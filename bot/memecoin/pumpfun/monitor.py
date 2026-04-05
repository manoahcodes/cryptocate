"""
Feature 14 — Pump.fun bonding curve milestone monitor (Pro only).

Uses the `pumpfun` PyPI library (pip install pumpfun==0.3) which wraps
the Pump.fun frontend API. No API key or wallet required — read-only.

Reference: https://pypi.org/project/pumpfun/
"""

import logging

import redis
from django.conf import settings

logger = logging.getLogger(__name__)

# Milestone thresholds as % of graduation market cap
MILESTONES_PCT = [25, 50, 75, 90, 100]


def _get_redis() -> redis.Redis:
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


# ── pumpfun library helpers ────────────────────────────────────────────────────

def get_coin(mint_address: str) -> dict | None:
    """
    Fetch a single Pump.fun token by mint address using the pumpfun library.
    Returns the coin dict or None on error.

    The pumpfun package exposes:
      get_coin(mint)       → single coin info
      get_all_trades(mint) → trade history
      get_sol_price()      → current SOL/USD price

    from pumpfun import get_coin, get_all_trades, get_sol_price
    """
    try:
        from pumpfun import get_coin as _get_coin
        return _get_coin(mint=mint_address)
    except ImportError:
        logger.warning(
            "pumpfun library not installed — run: pip install pumpfun==0.3\n"
            "Falling back to direct API call."
        )
        return _get_coin_direct(mint_address)
    except Exception as e:
        logger.error("pumpfun get_coin failed for %s: %s", mint_address[:12], e)
        return None


def get_recent_trades(mint_address: str, limit: int = 20) -> list[dict]:
    """
    Fetch recent trades for a Pump.fun token.
    Used by whale_entry detector to spot large buys.
    """
    try:
        from pumpfun import get_all_trades
        trades = get_all_trades(mint=mint_address, limit=limit)
        return trades if isinstance(trades, list) else []
    except ImportError:
        logger.warning("pumpfun library not installed — pip install pumpfun==0.3")
        return []
    except Exception as e:
        logger.error("pumpfun get_all_trades failed for %s: %s", mint_address[:12], e)
        return []


def get_sol_price_usd() -> float | None:
    """Fetch current SOL/USD price via the pumpfun library."""
    try:
        from pumpfun import get_sol_price
        price = get_sol_price()
        return float(price) if price else None
    except ImportError:
        logger.warning("pumpfun library not installed — pip install pumpfun==0.3")
        return None
    except Exception as e:
        logger.error("pumpfun get_sol_price failed: %s", e)
        return None


def _get_coin_direct(mint_address: str) -> dict | None:
    """
    Fallback: call the Pump.fun frontend API directly if the
    pumpfun library is not installed.
    """
    import requests
    try:
        resp = requests.get(
            f"https://frontend-api-v3.pump.fun/coins/{mint_address}",
            timeout=10,
            headers={"Accept": "application/json"},
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error("Direct Pump.fun API call failed for %s: %s", mint_address[:12], e)
        return None


# ── Milestone checker ──────────────────────────────────────────────────────────

def check_pumpfun_milestones(token) -> list[dict]:
    """
    Check a MemeToken for Pump.fun bonding curve milestones.
    Fetches live data via the pumpfun library.

    Returns a list of new milestone alert dicts not previously sent.
    token: MemeToken instance with is_pump_fun=True
    """
    if not token.is_pump_fun:
        return []

    coin = get_coin(token.address)
    if not coin:
        return _check_milestones_from_mcap(token)

    # pumpfun library / frontend API coin fields:
    #   bonding_curve_progress  → float 0.0–1.0
    #   complete                → bool, True when graduated
    #   usd_market_cap          → float
    #   symbol, name, mint
    is_complete  = bool(coin.get("complete", False))
    raw_progress = coin.get("bonding_curve_progress", 0) or 0
    current_mcap = float(coin.get("usd_market_cap") or 0)

    progress_pct = 100.0 if is_complete else min(float(raw_progress) * 100, 100.0)

    _sync_token_data(token, coin, progress_pct, is_complete)

    return _evaluate_milestones(token, progress_pct, current_mcap, is_complete)


def _check_milestones_from_mcap(token) -> list[dict]:
    """Estimate progress from stored market cap when the API is unavailable."""
    grad_mcap    = settings.PUMP_FUN_GRADUATION_MCAP
    current_mcap = token.market_cap_usd or 0
    if current_mcap <= 0 or grad_mcap <= 0:
        return []
    progress_pct = min((current_mcap / grad_mcap) * 100, 100.0)
    is_complete  = progress_pct >= 100
    return _evaluate_milestones(token, progress_pct, current_mcap, is_complete)


def _sync_token_data(token, coin: dict, progress_pct: float, is_complete: bool) -> None:
    """Write fresh Pump.fun data back to the MemeToken record."""
    from bot.memecoin.models import MemeToken
    from django.utils import timezone

    updates = {
        "bonding_curve_pct": progress_pct,
        "market_cap_usd":    coin.get("usd_market_cap") or token.market_cap_usd,
        "symbol":            coin.get("symbol") or token.symbol,
        "name":              coin.get("name")   or token.name,
    }
    if is_complete and token.status != MemeToken.STATUS_GRADUATED:
        updates["status"]       = MemeToken.STATUS_GRADUATED
        updates["graduated_at"] = timezone.now()

    MemeToken.objects.filter(pk=token.pk).update(**updates)


def _evaluate_milestones(
    token,
    progress_pct: float,
    current_mcap: float,
    is_complete: bool,
) -> list[dict]:
    """Return only milestones crossed that haven't been alerted yet."""
    r           = _get_redis()
    alerted_key = f"pumpfun_milestones:{token.address}"
    already     = set(r.smembers(alerted_key))
    grad_mcap   = settings.PUMP_FUN_GRADUATION_MCAP

    new_alerts = []
    for milestone in MILESTONES_PCT:
        if progress_pct >= milestone and str(milestone) not in already:
            new_alerts.append({
                "milestone_pct":   milestone,
                "current_mcap":    current_mcap,
                "graduation_mcap": grad_mcap,
                "progress_pct":    progress_pct,
                "is_graduated":    is_complete or milestone >= 100,
            })
            r.sadd(alerted_key, str(milestone))
            r.expire(alerted_key, 86400 * 7)  # 7-day TTL

    return new_alerts


# ── Alert formatting ───────────────────────────────────────────────────────────

def format_pumpfun_alert(token, milestone_data: dict) -> str:
    symbol       = token.symbol or "?"
    milestone    = milestone_data["milestone_pct"]
    mcap         = milestone_data["current_mcap"]
    grad_mcap    = milestone_data["graduation_mcap"]
    progress_pct = milestone_data.get("progress_pct", float(milestone))
    is_graduated = milestone_data.get("is_graduated", False)

    if is_graduated:
        return (
            f"🎓 <b>Pump.fun Graduation!</b>\n\n"
            f"Token: <b>{symbol}</b>\n"
            f"Market Cap: ${mcap:,.0f}\n\n"
            f"✅ Graduated from bonding curve!\n"
            f"Now trading on Raydium. \n\n"
            f"Address: <code>{token.address[:16]}</code>\n"
            f"[View on Pump.fun](https://pump.fun/{token.address})"
        )

    filled = int(progress_pct / 10)
    bar    = "█" * filled + "░" * (10 - filled)

    return (
        f"📈 <b>Pump.fun — {milestone}% Milestone</b>\n\n"
        f"Token: <b>{symbol}</b>\n"
        f"Progress: <code>{bar}</code> {progress_pct:.1f}%\n"
        f"Market Cap: ${mcap:,.0f} / ${grad_mcap:,.0f}\n\n"
        f"Address: <code>{token.address[:16]}<code>\n"
        f"[View on Pump.fun](https://pump.fun/{token.address})\n"
        f"Graduates at ${grad_mcap:,.0f} MC"
    )


# ── Batch runner ───────────────────────────────────────────────────────────────

def alert_pumpfun_milestones_for_all(pro_users) -> int:
    """
    Check all active Pump.fun tokens for milestone crossings
    and alert all Pro users. Returns total alerts sent.
    """
    from bot.core.tasks import send_alert_message
    from bot.memecoin.models import MemeAlert, MemeToken

    pump_tokens = MemeToken.objects.filter(
        is_pump_fun=True,
        status=MemeToken.STATUS_WATCHING,
    )

    total_sent = 0
    for token in pump_tokens:
        try:
            milestones = check_pumpfun_milestones(token)
        except Exception as e:
            logger.error("Milestone check failed for %s: %s", token.address[:12], e)
            continue

        for milestone_data in milestones:
            message = format_pumpfun_alert(token, milestone_data)
            for user in pro_users:
                try:
                    send_alert_message.delay(user.telegram_id, message)
                    MemeAlert.objects.create(
                        telegram_user=user,
                        token=token,
                        alert_type=MemeAlert.ALERT_PUMP_GRADUATION,
                        message_sent=message,
                    )
                    total_sent += 1
                except Exception as e:
                    logger.warning(
                        "Pump.fun alert failed for user %s: %s",
                        user.telegram_id, e,
                    )

    return total_sent


# ── New coin discovery ─────────────────────────────────────────────────────────

def discover_new_pumpfun_tokens(limit: int = 20) -> list:
    """
    Fetch the latest Pump.fun launches using the pumpfun library
    and upsert them as MemeToken records.
    Returns list of newly created MemeToken instances.
    """
    from bot.memecoin.models import MemeToken

    # pumpfun library doesn't expose a "list new coins" function directly,
    # so we fall back to the frontend API for discovery
    import requests
    try:
        resp = requests.get(
            "https://frontend-api-v3.pump.fun/coins",
            params={
                "sort":         "created_timestamp",
                "order":        "DESC",
                "limit":        limit,
                "includeNsfw":  "false",
            },
            timeout=10,
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        coins = resp.json()
        if not isinstance(coins, list):
            return []
    except Exception as e:
        logger.error("Pump.fun new coin discovery failed: %s", e)
        return []

    created = []
    for coin in coins:
        mint = coin.get("mint", "")
        if not mint:
            continue

        raw_progress = coin.get("bonding_curve_progress", 0) or 0
        try:
            progress_pct = float(raw_progress) * 100
        except (TypeError, ValueError):
            progress_pct = 0.0

        token, was_created = MemeToken.objects.get_or_create(
            address=mint,
            chain="sol",
            defaults={
                "symbol":            coin.get("symbol", ""),
                "name":              coin.get("name", ""),
                "is_pump_fun":       True,
                "status":            MemeToken.STATUS_WATCHING,
                "market_cap_usd":    coin.get("usd_market_cap"),
                "bonding_curve_pct": progress_pct,
            },
        )
        if was_created:
            created.append(token)

    logger.info(
        "discover_new_pumpfun_tokens: fetched=%d new=%d",
        len(coins), len(created),
    )
    return created