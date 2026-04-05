"""
Feature 3 — Whale directory helpers.
Formats directory data for Telegram display using HTML parse mode.
"""

from html import escape as he

from bot.directory.models import DirectoryWallet


def get_directory_summary(chain: str = None, category: str = None, limit: int = 10) -> str:
    """
    Build an HTML-formatted Telegram message listing whale directory entries.
    """
    qs = DirectoryWallet.objects.filter(is_active=True)
    if chain:
        qs = qs.filter(chain=chain)
    if category:
        qs = qs.filter(category=category)

    total   = qs.count()
    wallets = qs[:limit]

    if not wallets:
        return "🐋 <b>Whale Directory</b>\n\nNo entries found."

    lines = [
        "🐋 <b>Whale Directory</b>",
        f"<i>{total} tracked wallets</i>",
        "",
    ]

    for w in wallets:
        verified = " ✅" if w.is_verified else ""
        label    = he(w.label)
        address  = he(w.address)
        chain_str = w.chain.upper()
        category_str = w.category.replace("_", " ").title()

        lines.append(
            f"• <b>{label}</b>{verified} [{chain_str}]\n"
            f"  <code>{address}…</code> — {category_str}"
        )

    lines.extend([
        "",
        "<i>Use /add to track any of these wallets</i>",
    ])

    return "\n".join(lines)


def lookup_wallet_label(address: str, chain: str = "eth") -> str:
    """
    Return a directory label for a wallet address if it exists.
    Used to enrich alert messages with whale identities.
    """
    try:
        entry = DirectoryWallet.objects.get(
            address__iexact=address,
            chain=chain,
            is_active=True,
        )
        return entry.label
    except DirectoryWallet.DoesNotExist:
        return ""