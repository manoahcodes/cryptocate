"""
Feature 7 — Wallet profitability score calculator (Pro only).
Scores are 0–10 based on win rate, average return, and trade count.
Recalculated weekly by the Celery beat task.
"""

import logging
from typing import Optional

from bot.blockchain.etherscan import get_transactions
from bot.core.models import WalletScore, WatchedWallet

logger = logging.getLogger(__name__)

# Minimum trades required for a meaningful score
MIN_TRADES = 5
# Analysis window in transactions
TX_SAMPLE = 100


def calculate_wallet_score(wallet: WatchedWallet) -> Optional[WalletScore]:
    """
    Calculate and persist a profitability score for a wallet.
    Returns the WalletScore instance or None on failure.

    Scoring methodology:
      - Fetch the last TX_SAMPLE transactions
      - Identify "trade pairs" (buy/sell cycles) by value sign changes
      - Calculate win rate and average return
      - Composite score = (win_rate * 6) + (avg_return_normalised * 4), capped at 10
    """
    try:
        txs = get_transactions(wallet.address, wallet.chain, offset=TX_SAMPLE)
    except Exception as e:
        logger.error("Failed to fetch txs for scoring %s: %s", wallet.address, e)
        return None

    if len(txs) < MIN_TRADES:
        logger.debug(
            "Not enough transactions (%d) to score wallet %s",
            len(txs),
            wallet.address,
        )
        # Record a pending score
        score_obj, _ = WalletScore.objects.update_or_create(
            wallet=wallet,
            defaults={
                "score": 0.0,
                "win_rate": 0.0,
                "avg_return_pct": 0.0,
                "total_trades": len(txs),
            },
        )
        return score_obj

    wallet_addr = wallet.address.lower()

    # Separate inflows and outflows by value
    inflows = []
    outflows = []

    for tx in txs:
        try:
            value_eth = int(tx.get("value", 0)) / 1e18
            is_error = tx.get("isError", "0") == "1"
            if is_error or value_eth < 0.001:
                continue

            from_addr = tx.get("from", "").lower()
            if from_addr == wallet_addr:
                outflows.append(value_eth)
            else:
                inflows.append(value_eth)
        except (ValueError, TypeError):
            continue

    total_trades = len(inflows) + len(outflows)
    if total_trades < MIN_TRADES:
        score_obj, _ = WalletScore.objects.update_or_create(
            wallet=wallet,
            defaults={
                "score": 0.0,
                "win_rate": 0.0,
                "avg_return_pct": 0.0,
                "total_trades": total_trades,
            },
        )
        return score_obj

    # Simplified win-rate: ratio of inflow txs to total (more inflows = net accumulation)
    total_inflow = sum(inflows)
    total_outflow = sum(outflows)

    win_rate = len(inflows) / total_trades if total_trades > 0 else 0.0

    # Average return proxy: (inflow - outflow) / outflow if outflow > 0
    avg_return_pct = 0.0
    if total_outflow > 0:
        avg_return_pct = ((total_inflow - total_outflow) / total_outflow) * 100

    # Composite score (0–10)
    # win_rate component: 0–6
    win_component = min(win_rate * 6.0, 6.0)
    # avg_return component: 0–4, normalised at 50% return = full 4 pts
    return_component = min(max(avg_return_pct / 50.0, 0.0) * 4.0, 4.0)

    score = round(win_component + return_component, 2)
    score = max(0.0, min(score, 10.0))

    score_obj, _ = WalletScore.objects.update_or_create(
        wallet=wallet,
        defaults={
            "score": score,
            "win_rate": round(win_rate, 4),
            "avg_return_pct": round(avg_return_pct, 2),
            "total_trades": total_trades,
        },
    )

    logger.info(
        "Scored wallet %s (%s): %.1f/10 (win_rate=%.0f%%, avg_return=%.1f%%)",
        wallet.address[:12],
        wallet.chain,
        score,
        win_rate * 100,
        avg_return_pct,
    )

    return score_obj
