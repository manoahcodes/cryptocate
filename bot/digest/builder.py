"""
Feature 2 — Daily digest builder.
Compiles a summary of wallet activity for the past 24 hours.
Uses HTML parse mode throughout.
"""

import logging
from datetime import timedelta
from html import escape as he

from django.utils import timezone

from bot.core.models import Alert, TelegramUser
from bot.prices.coingecko import format_usd

logger = logging.getLogger(__name__)


def build_digest(tg_user: TelegramUser) -> str:
    """
    Build an HTML digest message for a Pro user covering the last 24 hours.
    Returns an empty string if the user has no wallets.

    Note: tg_user.wallets works via the reverse FK relation:
      WatchedWallet.telegram_user = ForeignKey(TelegramUser, related_name="wallets")
    """
    since = timezone.now() - timedelta(hours=24)

    wallets = tg_user.wallets.all()
    if not wallets.exists():
        return ""

    alerts = (
        Alert.objects.filter(
            telegram_user=tg_user,
            sent_at__gte=since,
        )
        .select_related("wallet")
        .order_by("-sent_at")
    )

    if not alerts.exists():
        return (
            "📰 <b>Daily Digest</b>\n\n"
            "No wallet activity in the last 24 hours.\n"
            "Your whales are quiet 🤫"
        )

    # Aggregate stats
    total_alerts  = alerts.count()
    total_usd     = sum(a.amount_usd or 0 for a in alerts)
    inflow_count  = alerts.filter(direction="in").count()
    outflow_count = alerts.filter(direction="out").count()
    date_str      = timezone.now().strftime("%Y-%m-%d")

    lines = [
        f"📰 <b>Daily Digest</b> — {date_str}",
        "",
        "📊 <b>Summary (last 24h)</b>",
        f"• Alerts fired: {total_alerts}",
        f"• Total volume: {format_usd(total_usd)}",
        f"• Inflows: {inflow_count} · Outflows: {outflow_count}",
        "",
        "━━━━━━━━━━━━━━━━━━",
        "<b>Recent Movements</b>",
        "",
    ]

    for alert in alerts[:10]:
        wallet_str = ""
        if alert.wallet:
            label      = he(alert.wallet.label or f"{alert.wallet.address[:8]}…")
            wallet_str = f"[{label}] "

        direction_emoji = "📥" if alert.direction == "in" else "📤"
        exchange        = f" via {he(alert.exchange_label)}" if alert.exchange_label else ""
        amount_str      = f"{alert.amount_eth:.2f} ETH" if alert.amount_eth else ""
        usd_str         = f" ({format_usd(alert.amount_usd)})" if alert.amount_usd else ""
        token_str       = f" {he(alert.token_symbol)}" if alert.token_symbol else ""

        lines.append(
            f"{direction_emoji} {wallet_str}"
            f"<code>{amount_str}{token_str}</code>{usd_str}{exchange}"
        )

    if total_alerts > 10:
        lines.append(f"\n<i>…and {total_alerts - 10} more alerts</i>")

    # Wallet scores section
    score_lines = []
    for wallet in wallets[:5]:
        try:
            score     = wallet.score.score
            win_rate  = wallet.score.win_rate
            label     = he(wallet.label or f"{wallet.address[:8]}…")
            score_lines.append(
                f"• {label}: <b>{score:.1f}/10</b> "
                f"<i>(win rate {win_rate:.0%})</i>"
            )
        except Exception:
            pass

    if score_lines:
        lines.extend([
            "",
            "━━━━━━━━━━━━━━━━━━",
            "<b>Wallet Scores</b> (Pro)",
            "",
        ])
        lines.extend(score_lines)

    lines.append("\n<i>Run /status for full account info</i>")

    return "\n".join(lines)