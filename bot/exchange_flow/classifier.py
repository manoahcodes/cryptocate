"""
Feature 5 — Exchange inflow/outflow classification (Free + Pro).
Labels every ETH transfer alert with the exchange name if known.
"""

from bot.blockchain.exchanges import classify_transfer, get_exchange_label


def classify_transaction(tx: dict, wallet_address: str) -> dict:
    """
    Classify a transaction's exchange context.

    Returns a dict with:
        direction:      "in" | "out" | ""
        exchange_label: e.g. "Binance" | ""
        flow_type:      "exchange_inflow" | "exchange_outflow" | "wallet_to_wallet" | "unknown"
        signal:         "accumulation" | "distribution" | "transfer" | ""
    """
    from_addr = tx.get("from", "").lower()
    to_addr = tx.get("to", "").lower()
    wallet_addr = wallet_address.lower()

    direction = "out" if from_addr == wallet_addr else "in"
    exchange_direction, exchange_label = classify_transfer(from_addr, to_addr)

    flow_type = "unknown"
    signal = ""

    if exchange_label:
        if exchange_direction == "outflow":
            # Whale depositing TO exchange — possible sell signal
            flow_type = "exchange_outflow"
            signal = "distribution"
        elif exchange_direction == "inflow":
            # Whale receiving FROM exchange — possible buy/accumulation signal
            flow_type = "exchange_inflow"
            signal = "accumulation"
    else:
        # Check if either side is a known DEX
        from_label = get_exchange_label(from_addr)
        to_label = get_exchange_label(to_addr)
        if from_label or to_label:
            exchange_label = from_label or to_label
            flow_type = "dex_trade"
            signal = "transfer"
        else:
            flow_type = "wallet_to_wallet"
            signal = "transfer"

    return {
        "direction": direction,
        "exchange_label": exchange_label,
        "flow_type": flow_type,
        "signal": signal,
    }


def format_flow_label(classification: dict) -> str:
    """
    Format a human-readable flow label for alert messages.
    E.g. "→ Binance (distribution)" or "← Coinbase (accumulation)"
    """
    exchange = classification.get("exchange_label", "")
    signal = classification.get("signal", "")
    direction = classification.get("direction", "")

    if not exchange:
        return ""

    arrow = "→" if direction == "out" else "←"
    signal_text = f" \\({signal}\\)" if signal and signal != "transfer" else ""

    return f"{arrow} {exchange}{signal_text}"
