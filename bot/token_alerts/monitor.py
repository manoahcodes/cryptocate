"""
Feature 4 — ERC-20 token transfer alerts (Pro only).
Fires when a watched wallet moves tokens worth >= $10,000 USD.
"""

import logging

from bot.blockchain.etherscan import get_token_transfers
from bot.core.models import Alert, WatchedWallet
from bot.prices.coingecko import format_usd, get_price_usd

logger = logging.getLogger(__name__)

TOKEN_ALERT_THRESHOLD_USD = 10_000.0

# CoinGecko IDs for common ERC-20 tokens by symbol
TOKEN_PRICES: dict[str, str] = {
    "USDC": "usd-coin",
    "USDT": "tether",
    "DAI": "dai",
    "WBTC": "wrapped-bitcoin",
    "LINK": "chainlink",
    "UNI": "uniswap",
    "AAVE": "aave",
    "CRV": "curve-dao-token",
    "LDO": "lido-dao",
    "SHIB": "shiba-inu",
    "PEPE": "pepe",
    "ARB": "arbitrum",
    "OP": "optimism",
}


def get_token_price_usd(symbol: str) -> float:
    """Return the USD price for a token symbol. Returns 1.0 for stablecoins."""
    if symbol.upper() in ("USDC", "USDT", "DAI", "BUSD", "TUSD", "FRAX", "LUSD"):
        return 1.0
    coin_id = TOKEN_PRICES.get(symbol.upper())
    if coin_id:
        price = get_price_usd(coin_id)
        return price or 0.0
    return 0.0


def check_token_transfers(wallet: WatchedWallet) -> list[dict]:
    """
    Fetch recent ERC-20 transfers for a wallet and return those
    meeting the $10K USD threshold that haven't been alerted yet.
    Pro-only feature — caller must verify plan before calling.
    """
    txs = get_token_transfers(wallet.address, wallet.chain, offset=10)
    new_alerts = []

    alerted_hashes = set(
        Alert.objects.filter(
            wallet=wallet,
            alert_type="token",
        ).values_list("tx_hash", flat=True)
    )

    for tx in txs:
        tx_hash = tx.get("hash", "")
        if tx_hash in alerted_hashes:
            continue

        try:
            symbol = tx.get("tokenSymbol", "?")
            decimals = int(tx.get("tokenDecimal", 18))
            raw_value = int(tx.get("value", 0))
            token_amount = raw_value / (10 ** decimals)

            price_usd = get_token_price_usd(symbol)
            value_usd = token_amount * price_usd

            if value_usd < TOKEN_ALERT_THRESHOLD_USD:
                continue

            from_addr = tx.get("from", "").lower()
            to_addr = tx.get("to", "").lower()
            wallet_addr = wallet.address.lower()

            direction = "out" if from_addr == wallet_addr else "in"

            new_alerts.append({
                "tx_hash": tx_hash,
                "symbol": symbol,
                "token_amount": token_amount,
                "value_usd": value_usd,
                "direction": direction,
                "from_address": from_addr,
                "to_address": to_addr,
            })

        except (ValueError, TypeError) as e:
            logger.debug("Token transfer parse error for tx %s: %s", tx_hash, e)

    return new_alerts


def format_token_alert(wallet: WatchedWallet, alert_data: dict) -> str:
    """Format a token transfer alert as a Telegram Markdown message."""
    from bot.blockchain.exchanges import get_exchange_label

    direction = alert_data["direction"]
    symbol = alert_data["symbol"]
    amount = alert_data["token_amount"]
    value_usd = alert_data["value_usd"]
    tx_hash = alert_data["tx_hash"]

    direction_emoji = "📥" if direction == "in" else "📤"
    direction_label = "Received" if direction == "in" else "Sent"

    label = wallet.label or f"{wallet.address[:10]}…"

    # Exchange label
    counterpart = (
        alert_data["from_address"]
        if direction == "in"
        else alert_data["to_address"]
    )
    exchange = get_exchange_label(counterpart)
    exchange_text = f" \\({exchange}\\)" if exchange else ""

    amount_fmt = f"{amount:,.2f}" if amount < 10_000 else f"{amount:,.0f}"

    chain_explorer = {
        "eth": "https://etherscan.io/tx",
        "arb": "https://arbiscan.io/tx",
        "base": "https://basescan.org/tx",
        "bsc": "https://bscscan.com/tx",
    }.get(wallet.chain, "https://etherscan.io/tx")

    return (
        f"{direction_emoji} *Token Alert — {label}*\n\n"
        f"{direction_label} *{amount_fmt} {symbol}*{exchange_text}\n"
        f"Value: *{format_usd(value_usd)}*\n"
        f"Chain: {wallet.chain.upper()}\n"
        f"[View TX]({chain_explorer}/{tx_hash})"
    )
