"""
Feature 9 — Multi-chain router.
Routes wallet polling to the correct chain API and dispatches alerts.
Chains: ETH (free + pro), ARB / BASE / BSC / SOL (pro only).
"""

import logging

from django.utils import timezone

from bot.blockchain.exchanges import classify_transfer
from bot.core.models import Alert, WatchedWallet
from bot.prices.coingecko import eth_to_usd, format_usd
from bot.thresholds.resolver import meets_threshold

logger = logging.getLogger(__name__)


def check_wallet_for_alerts(wallet: WatchedWallet) -> int:
    """
    Check a single wallet for new transactions and dispatch alerts.
    Returns the number of alerts sent.

    - ETH only for free users
    - All 5 chains for Pro users
    """
    user = wallet.telegram_user

    # Free users can only track ETH
    if not user.is_pro() and wallet.chain != "eth":
        return 0

    if wallet.chain == "sol":
        return _check_solana_wallet(wallet)
    else:
        return _check_evm_wallet(wallet)


def _check_evm_wallet(wallet: WatchedWallet) -> int:
    """Check an EVM-compatible wallet (ETH / ARB / BASE / BSC)."""
    from bot.blockchain.etherscan import get_transactions

    try:
        txs = get_transactions(
            wallet.address,
            wallet.chain,
            page=1,
            offset=5,
        )
    except Exception as e:
        logger.warning("Failed to fetch txs for %s (%s): %s", wallet.address, wallet.chain, e)
        return 0

    if not txs:
        _update_wallet_checked(wallet)
        return 0

    alerts_sent = 0
    wallet_addr = wallet.address.lower()

    # Collect already-alerted tx hashes to avoid duplicates
    alerted_hashes = set(
        Alert.objects.filter(wallet=wallet).values_list("tx_hash", flat=True)
    )

    for tx in txs:
        tx_hash = tx.get("hash", "")
        if not tx_hash or tx_hash in alerted_hashes:
            continue

        # Skip failed transactions
        if tx.get("isError", "0") == "1":
            continue

        try:
            value_wei = int(tx.get("value", 0))
            amount_eth = value_wei / 1e18
        except (ValueError, TypeError):
            continue

        if not meets_threshold(amount_eth, wallet):
            continue

        from_addr = tx.get("from", "").lower()
        to_addr = tx.get("to", "").lower()
        direction = "out" if from_addr == wallet_addr else "in"

        # Exchange classification (free + pro feature)
        _, exchange_label = classify_transfer(from_addr, to_addr)

        # USD value
        amount_usd = eth_to_usd(amount_eth, wallet.chain)

        # Save alert record
        alert = Alert.objects.create(
            telegram_user=wallet.telegram_user,
            wallet=wallet,
            alert_type="transfer",
            tx_hash=tx_hash,
            amount_eth=amount_eth,
            amount_usd=amount_usd,
            direction=direction,
            exchange_label=exchange_label or "",
        )

        # Format and send message
        message = _format_evm_alert(wallet, tx_hash, amount_eth, amount_usd,
                                    direction, exchange_label)
        alert.message_sent = message
        alert.save(update_fields=["message_sent"])

        _send_alert(wallet.telegram_user.telegram_id, message)

        # Check dormant reactivation (Pro only)
        if wallet.telegram_user.is_pro():
            _check_dormant_and_alert(wallet, tx_hash)

        # Check ERC-20 token transfers (Pro only)
        if wallet.telegram_user.is_pro():
            _check_token_transfers_and_alert(wallet)

        # Copy-trade signal (Pro, score >= 7.0)
        if wallet.telegram_user.is_pro():
            _maybe_send_copy_trade_signal(wallet, tx, amount_eth, direction)

        alerts_sent += 1

    # Update last seen tx
    if txs and txs[0].get("hash") != wallet.last_seen_tx:
        wallet.last_seen_tx = txs[0].get("hash", "")

    _update_wallet_checked(wallet)
    return alerts_sent


def _check_solana_wallet(wallet: WatchedWallet) -> int:
    """
    Check a Solana wallet for new transactions via Solscan Pro API v2.0.

    Solscan v2.0 transaction fields:
      tx_hash   — transaction signature
      fee       — fee in lamports
      sol_transfer → amount  — SOL transferred in lamports (if SOL transfer)
      block_time — unix timestamp

    Reference: https://pro-api.solscan.io/pro-api-docs/v2.0
    """
    from html import escape as he
    from bot.blockchain.solscan import get_sol_transactions

    try:
        txs = get_sol_transactions(wallet.address, limit=5)
    except Exception as e:
        logger.warning("Failed to fetch SOL txs for %s: %s", wallet.address, e)
        return 0

    if not txs:
        _update_wallet_checked(wallet)
        return 0

    alerted_hashes = set(
        Alert.objects.filter(wallet=wallet).values_list("tx_hash", flat=True)
    )

    alerts_sent = 0
    for tx in txs:
        # Solscan v2.0 uses tx_hash as the signature field
        sig = tx.get("tx_hash") or tx.get("signature") or tx.get("txHash") or ""
        if not sig or sig in alerted_hashes:
            continue

        # Public API fields:
        #   lamport  — SOL change in lamports (can be negative = sent)
        #   signer   — list of signing addresses
        sol_amount = 0.0
        try:
            lamports   = tx.get("lamport") or 0
            sol_amount = abs(int(lamports) / 1e9)
        except (ValueError, TypeError):
            sol_amount = 0.0

        if not meets_threshold(sol_amount, wallet):
            continue

        # Direction: if wallet is in the signer list it initiated the tx (out)
        signers    = tx.get("signer") or []
        wallet_addr = wallet.address.lower()
        if isinstance(signers, list):
            direction = "out" if any(
                str(s).lower() == wallet_addr for s in signers
            ) else "in"
        else:
            direction = "out"

        amount_usd = eth_to_usd(sol_amount, "sol")

        Alert.objects.create(
            telegram_user=wallet.telegram_user,
            wallet=wallet,
            alert_type="transfer",
            tx_hash=sig,
            amount_eth=sol_amount,
            amount_usd=amount_usd,
            direction=direction,
            exchange_label="",
        )

        # HTML parse mode — no MarkdownV2 escaping needed
        label      = he(wallet.label or f"{wallet.address[:10]}…")
        direction_emoji = "📤" if direction == "out" else "📥"
        usd_str    = f" ({format_usd(amount_usd)})" if amount_usd else ""
        sig_short  = he(sig[:16])

        message = (
            f"{direction_emoji} <b>Whale Movement \u2014 {label}</b>\n\n"
            f"<b>{sol_amount:.4f} SOL</b>{usd_str}\n"
            f"Chain: Solana\n"
            f"<a href=\"https://solscan.io/tx/{sig}\">View Transaction</a>"
        )
        _send_alert(wallet.telegram_user.telegram_id, message, parse_mode="HTML")
        alerts_sent += 1

    _update_wallet_checked(wallet)
    return alerts_sent


def _format_evm_alert(
    wallet: WatchedWallet,
    tx_hash: str,
    amount_eth: float,
    amount_usd: float | None,
    direction: str,
    exchange_label: str,
) -> str:
    """Format an EVM transfer alert as Telegram Markdown."""
    label = wallet.label or f"{wallet.address[:10]}…"
    direction_emoji = "📥" if direction == "in" else "📤"
    direction_label = "Received" if direction == "in" else "Sent"

    coin_symbol = {
        "eth": "ETH",
        "arb": "ETH",
        "base": "ETH",
        "bsc": "BNB",
        "sol": "SOL",
    }.get(wallet.chain, "ETH")

    usd_str = f" \\({format_usd(amount_usd)}\\)" if amount_usd else ""

    exchange_str = ""
    if exchange_label:
        arrow = "→" if direction == "out" else "←"
        exchange_str = f"\n{arrow} *{exchange_label}*"

    chain_explorer = {
        "eth": "https://etherscan.io/tx",
        "arb": "https://arbiscan.io/tx",
        "base": "https://basescan.org/tx",
        "bsc": "https://bscscan.com/tx",
    }.get(wallet.chain, "https://etherscan.io/tx")

    return (
        f"{direction_emoji} *Whale Movement — {label}*\n\n"
        f"{direction_label} *{amount_eth:.4f} {coin_symbol}*{usd_str}{exchange_str}\n"
        f"Chain: {wallet.chain.upper()}\n"
        f"[View TX]({chain_explorer}/{tx_hash})"
    )


def _update_wallet_checked(wallet: WatchedWallet) -> None:
    """Update last_checked_at timestamp."""
    WatchedWallet.objects.filter(pk=wallet.pk).update(
        last_checked_at=timezone.now(),
        last_seen_tx=wallet.last_seen_tx,
    )


def _send_alert(telegram_id: int, message: str, parse_mode: str = "HTML") -> None:
    """Dispatch alert message via Celery."""
    try:
        from bot.core.tasks import send_alert_message
        send_alert_message.delay(telegram_id, message, parse_mode=parse_mode)
    except Exception as e:
        logger.error("Failed to queue alert for %s: %s", telegram_id, e)


def _check_dormant_and_alert(wallet: WatchedWallet, tx_hash: str) -> None:
    """
    Fire a dormant wallet reactivation alert if applicable.

    Uses check_dormant_reactivation() which:
      1. Fetches the latest transaction from the chain
      2. Checks whether the wallet was inactive for >= 90 days before it
      3. Returns alert data if reactivation is detected, None otherwise

    We do NOT use is_wallet_dormant() here because that only checks
    last_checked_at — which is about to be updated to now, so it would
    never trigger. check_dormant_reactivation() compares the actual
    on-chain transaction timestamp against the 90-day cutoff.
    """
    try:
        from bot.dormant.detector import (
            check_dormant_reactivation,
            format_dormant_alert,
        )

        alert_data = check_dormant_reactivation(wallet)
        if alert_data is None:
            return  # not dormant, or already alerted, or no new tx

        # Ensure the tx_hash from the current poll is used
        if not alert_data.get("tx_hash"):
            alert_data["tx_hash"] = tx_hash

        message = format_dormant_alert(wallet, alert_data)
        _send_alert(wallet.telegram_user.telegram_id, message)
        WatchedWallet.objects.filter(pk=wallet.pk).update(dormant_alerted=True)

        logger.info(
            "Dormant wallet reactivation alert sent for %s (%s)",
            wallet.address[:12], wallet.chain,
        )
    except Exception as e:
        logger.debug("Dormant check error for %s: %s", wallet.address, e)


def _check_token_transfers_and_alert(wallet: WatchedWallet) -> None:
    """Check and fire ERC-20 token transfer alerts."""
    try:
        from bot.token_alerts.monitor import check_token_transfers, format_token_alert

        token_alerts = check_token_transfers(wallet)
        for alert_data in token_alerts:
            message = format_token_alert(wallet, alert_data)
            Alert.objects.create(
                telegram_user=wallet.telegram_user,
                wallet=wallet,
                alert_type="token",
                tx_hash=alert_data["tx_hash"],
                amount_usd=alert_data["value_usd"],
                token_symbol=alert_data["symbol"],
                direction=alert_data["direction"],
                message_sent=message,
            )
            _send_alert(wallet.telegram_user.telegram_id, message)
    except Exception as e:
        logger.debug("Token transfer check error for %s: %s", wallet.address, e)


def _maybe_send_copy_trade_signal(
    wallet: WatchedWallet,
    tx: dict,
    amount_eth: float,
    direction: str,
) -> None:
    """Fire a copy-trade signal if the wallet scores >= 7.0."""
    try:
        from bot.copy_trade.signals import check_and_send_copy_trade_signal
        check_and_send_copy_trade_signal(wallet, tx, amount_eth, direction)
    except Exception as e:
        logger.debug("Copy-trade signal error for %s: %s", wallet.address, e)