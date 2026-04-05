"""
Feature 12 — RugCheck.xyz token safety analysis.
Free: 5 checks/hour (rate-limited in telegram_bot.py).
Pro: unlimited.

Reference: https://api.rugcheck.xyz/swagger/index.html
"""

import logging
from typing import Optional

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

RUGCHECK_BASE = "https://api.rugcheck.xyz/v1"
TIMEOUT = 15


def _get(endpoint: str, params: dict = None) -> Optional[dict]:
    headers = {}
    api_key = settings.RUGCHECK_API_KEY
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        resp = requests.get(
            f"{RUGCHECK_BASE}{endpoint}",
            params=params or {},
            headers=headers,
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.error("RugCheck API error (%s): %s", endpoint, e)
        return None


def check_token(token_address: str) -> str:
    """
    Run a rug check on a token address and return a formatted Telegram
    Markdown string with the safety summary.

    Tries RugCheck API first; falls back to a DexScreener liquidity check.
    """
    # Try rug check on Solana tokens via RugCheck
    data = _get(f"/tokens/{token_address}/report/summary")

    if data:
        return _format_rugcheck_result(token_address, data)

    # Fallback: use DexScreener data for a basic safety check
    return _fallback_dexscreener_check(token_address)


def _format_rugcheck_result(token_address: str, data: dict) -> str:
    """Format RugCheck API response as Telegram Markdown."""
    score = data.get("score", 0)
    risks = data.get("risks", [])
    token_meta = data.get("tokenMeta", {})

    symbol = token_meta.get("symbol", "?")
    name = token_meta.get("name", "?")

    # Risk level
    if score >= 700:
        risk_label = "🔴 HIGH RISK"
    elif score >= 400:
        risk_label = "🟠 MEDIUM RISK"
    elif score >= 100:
        risk_label = "🟡 LOW RISK"
    else:
        risk_label = "🟢 LOOKS SAFE"

    # Top risk items
    risk_lines = []
    for risk in risks[:5]:
        level = risk.get("level", "")
        name_r = risk.get("name", "")
        desc = risk.get("description", "")
        emoji = "🔴" if level == "danger" else "🟠" if level == "warn" else "ℹ️"
        risk_lines.append(f"{emoji} {name_r}: {desc[:60]}")

    risks_text = "\n".join(risk_lines) if risk_lines else "No major risks detected"

    return (
        f"🔍 <b>Rug Check — {symbol}</b>\n\n"
        f"Token: <b>{name}</b>\\(`{token_address[:16]}…`\\)\n"
        f"Risk Score: <b>{score}/1000</b>\n"
        f"Status: {risk_label}\n\n"
        f"<b>Risk Factors:</b>\n{risks_text}\n\n"
        f"Source: RugCheck\\.xyz"
    )


def _fallback_dexscreener_check(token_address: str) -> str:
    """Basic safety check using DexScreener when RugCheck is unavailable."""
    from bot.memecoin.scanner.dexscreener import get_token_pairs

    pairs = get_token_pairs(token_address)
    if not pairs:
        return (
            f"🔍 <b>Rug Check</b>\n\n"
            f"`{token_address[:16]}…`\n\n"
            f"❌ Token not found on any DEX\\.\n"
            f"Could not complete rug check — no liquidity found\\."
        )

    best_pair = max(pairs, key=lambda p: p.get("liquidity", {}).get("usd", 0))
    liq = best_pair.get("liquidity", {}).get("usd", 0) or 0
    symbol = best_pair.get("baseToken", {}).get("symbol", "?")
    dex = best_pair.get("dexId", "?")
    chain = best_pair.get("chainId", "?")

    # Basic risk heuristics
    warnings = []
    if liq < 10_000:
        warnings.append("⚠️ Very low liquidity \\(< \\$10K\\) — high rug risk")
    if liq < 50_000:
        warnings.append("🟠 Low liquidity \\(<b \\$50K\\)")
    if not warnings:
        warnings.append("🟢 Adequate liquidity found")

    warnings_text = "\n".join(warnings)

    return (
        f"🔍 <b>Rug Check — {symbol}</b>\n\n"
        f"Address: `{token_address[:16]}…`\n"
        f"Chain: {chain.upper()}\n"
        f"DEX: {dex}\n"
        f"Liquidity: \\${liq:,.0f}\n\n"
        f"<b>Analysis:</b>\n{warnings_text}\n\n"
        f"Basic check via DexScreener \\(RugCheck unavailable\\)"
    )


def cache_token_rugcheck(token_address: str, chain: str) -> None:
    """
    Run a rug check and cache the result on the MemeToken record.

    For Solana tokens: uses RugCheck.xyz API (has a score 0-1000).
    For EVM tokens:    RugCheck only supports Solana, so we fall back
                       to a liquidity-based heuristic via DexScreener
                       and store a synthetic score (0 = safe, 800 = risky).

    Always writes to:
      token.rugcheck_score        (float, 0-1000)
      token.rugcheck_summary      (str, comma-separated risk names)
      token.rugcheck_checked_at   (datetime)
    """
    from bot.memecoin.models import MemeToken

    try:
        token = MemeToken.objects.get(address=token_address.lower(), chain=chain)
    except MemeToken.DoesNotExist:
        logger.debug("cache_token_rugcheck: token not found %s", token_address[:12])
        return

    score   = None
    summary = ""

    if chain == "sol":
        # RugCheck.xyz supports Solana
        data = _get(f"/tokens/{token_address}/report/summary")
        if data:
            score   = float(data.get("score", 0))
            risks   = data.get("risks", [])
            summary = "; ".join(
                r.get("name", "") for r in risks[:5] if r.get("level") == "danger"
            )

    if score is None:
        # Fallback for EVM chains or when RugCheck API is unavailable:
        # derive a synthetic risk score from DexScreener liquidity
        score, summary = _evm_heuristic_score(token_address, chain)

    token.rugcheck_score       = score
    token.rugcheck_summary     = summary
    token.rugcheck_checked_at  = timezone.now()
    token.save(update_fields=["rugcheck_score", "rugcheck_summary", "rugcheck_checked_at"])
    logger.debug(
        "cache_token_rugcheck: %s (%s) score=%.0f summary=%r",
        token_address[:12], chain, score or 0, summary[:60],
    )


def _evm_heuristic_score(token_address: str, chain: str) -> tuple[float, str]:
    """
    Derive a synthetic rug-risk score for EVM tokens using DexScreener data.

    Score scale (mirrors RugCheck conventions):
      0   – 99   = low risk (green)
      100 – 399  = caution
      400 – 699  = medium risk (orange)
      700 – 1000 = high risk (red)

    Returns (score, summary_string).
    """
    try:
        from bot.memecoin.scanner.dexscreener import get_token_pairs

        pairs = get_token_pairs(token_address)
        if not pairs:
            # Cannot verify — treat as unknown/high risk
            return 750.0, "No DEX liquidity found"

        # Use highest-liquidity pair
        best  = max(pairs, key=lambda p: (p.get("liquidity") or {}).get("usd") or 0)
        liq   = (best.get("liquidity") or {}).get("usd") or 0
        buys  = (best.get("txns") or {}).get("h1", {}).get("buys") or 0
        sells = (best.get("txns") or {}).get("h1", {}).get("sells") or 0
        age_h = best.get("pairCreatedAt")  # ms timestamp

        risks = []
        score = 0.0

        if liq < 5_000:
            score += 400
            risks.append("Very low liquidity (<$5K)")
        elif liq < 20_000:
            score += 200
            risks.append("Low liquidity (<$20K)")
        elif liq < 100_000:
            score += 50

        if sells > 0 and buys > 0:
            sell_ratio = sells / (buys + sells)
            if sell_ratio > 0.8:
                score += 300
                risks.append("High sell pressure (>80% sells)")
            elif sell_ratio > 0.6:
                score += 100
                risks.append("Elevated sell pressure")

        if buys < 5 and sells < 5:
            score += 150
            risks.append("Very low trading activity")

        score = min(score, 1000.0)
        return score, "; ".join(risks) if risks else "No major risks detected"

    except Exception as e:
        logger.debug("_evm_heuristic_score failed for %s: %s", token_address[:12], e)
        return 500.0, "Score unavailable"