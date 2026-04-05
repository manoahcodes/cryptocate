"""
Feature 17 — NFT monitor: floor price, volume spikes, sweep detection,
and whale wallet NFT activity (EVM via Etherscan tokennfttx).
"""

import logging
from datetime import timedelta
from html import escape as he

import redis
from django.conf import settings
from django.utils import timezone

from bot.prices.coingecko import eth_to_usd, format_usd

logger = logging.getLogger(__name__)


def _get_redis() -> redis.Redis:
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


# ── Floor price alerts ────────────────────────────────────────────────────────

def check_floor_price(collection) -> list[dict]:
    """
    Check if floor price has dropped or risen beyond the user's thresholds.
    Works for Free and Pro users (Free: 1 collection).
    Returns list of alert dicts.
    """
    from bot.nft.opensea import get_collection_stats

    stats = get_collection_stats(collection.slug)
    if not stats:
        return []

    new_floor = float(stats.get("floor_price") or 0)
    if new_floor <= 0:
        return []

    # Cache latest data
    _update_collection_stats(collection, stats)

    prev_floor = collection.last_floor_alerted
    if prev_floor is None or prev_floor <= 0:
        # First check — save baseline, no alert
        from bot.nft.models import WatchedCollection
        WatchedCollection.objects.filter(pk=collection.pk).update(
            last_floor_alerted=new_floor,
            last_checked_at=timezone.now(),
        )
        return []

    alerts = []

    # Floor drop
    drop_pct = ((prev_floor - new_floor) / prev_floor) * 100
    if drop_pct >= collection.floor_drop_pct:
        alerts.append({
            "type":      "floor_drop",
            "new_floor": new_floor,
            "prev_floor": prev_floor,
            "change_pct": -drop_pct,
            "stats":     stats,
        })

    # Floor rise
    rise_pct = ((new_floor - prev_floor) / prev_floor) * 100
    if rise_pct >= collection.floor_rise_pct:
        alerts.append({
            "type":      "floor_rise",
            "new_floor": new_floor,
            "prev_floor": prev_floor,
            "change_pct": rise_pct,
            "stats":     stats,
        })

    if alerts:
        # Update the alerted floor so we don't re-alert the same level
        from bot.nft.models import WatchedCollection
        WatchedCollection.objects.filter(pk=collection.pk).update(
            last_floor_alerted=new_floor,
            last_checked_at=timezone.now(),
        )

    return alerts


def _update_collection_stats(collection, stats: dict) -> None:
    """Write fresh OpenSea stats to the WatchedCollection record."""
    from bot.nft.models import WatchedCollection
    from bot.prices.coingecko import get_price_usd

    floor_eth = stats.get("floor_price") or 0
    eth_price = get_price_usd("eth") or 0
    floor_usd = floor_eth * eth_price if floor_eth and eth_price else None

    WatchedCollection.objects.filter(pk=collection.pk).update(
        floor_price_eth  = floor_eth,
        floor_price_usd  = floor_usd,
        volume_24h       = stats.get("volume_24h"),
        num_owners       = stats.get("num_owners"),
        total_supply     = stats.get("total_supply"),
        last_checked_at  = timezone.now(),
    )


# ── Volume spike detection (Pro) ──────────────────────────────────────────────

def check_volume_spike(collection) -> list[dict]:
    """
    Alert when 1h volume exceeds the rolling baseline by collection.volume_spike_x.
    Pro only.
    """
    from bot.nft.opensea import get_collection_stats

    stats = get_collection_stats(collection.slug)
    if not stats:
        return []

    volume_24h = float(stats.get("volume_24h") or 0)
    if volume_24h <= 0:
        return []

    # Use 24h / 24 as a proxy for hourly volume
    volume_1h_estimate = volume_24h / 24

    baseline = collection.volume_baseline
    if baseline is None or baseline <= 0:
        # Seed baseline, no alert
        from bot.nft.models import WatchedCollection
        WatchedCollection.objects.filter(pk=collection.pk).update(
            volume_baseline=volume_1h_estimate
        )
        return []

    if volume_1h_estimate >= baseline * collection.volume_spike_x:
        # Update baseline (exponential moving average)
        new_baseline = baseline * 0.8 + volume_1h_estimate * 0.2
        from bot.nft.models import WatchedCollection
        WatchedCollection.objects.filter(pk=collection.pk).update(
            volume_baseline=new_baseline
        )
        return [{
            "type":       "volume_spike",
            "volume_1h":  volume_1h_estimate,
            "baseline":   baseline,
            "multiplier": volume_1h_estimate / baseline,
            "volume_24h": volume_24h,
        }]

    return []


# ── Sweep detection (Pro) ─────────────────────────────────────────────────────

def check_sweep(collection) -> list[dict]:
    """
    Alert when N distinct wallets buy the same collection within 1 hour.
    Uses OpenSea recent sales. Pro only.
    """
    from bot.nft.opensea import get_recent_sales

    sales = get_recent_sales(collection.slug, limit=50)
    if not sales:
        return []

    cutoff    = timezone.now() - timedelta(hours=1)
    recent    = [s for s in sales if s.get("timestamp", 0) >= cutoff.timestamp()]
    buyers    = set(s.get("buyer", "").lower() for s in recent if s.get("buyer"))

    if len(buyers) >= collection.sweep_min_wallets:
        r         = _get_redis()
        cache_key = f"nft_sweep_alerted:{collection.pk}"
        if not r.get(cache_key):
            r.setex(cache_key, 3600, "1")  # 1h cooldown
            total_vol = sum(s.get("price_eth", 0) for s in recent)
            return [{
                "type":         "sweep",
                "buyer_count":  len(buyers),
                "sale_count":   len(recent),
                "total_vol_eth": total_vol,
            }]

    return []


# ── Whale wallet NFT activity (Pro) ──────────────────────────────────────────

def check_whale_nft_activity(telegram_user) -> list[dict]:
    """
    Check all of a user's watched wallets for NFT transfers in the last poll.
    Uses Etherscan tokennfttx endpoint (free, already have key).
    Pro only.

    Returns list of activity dicts.
    """
    from bot.core.models import WatchedWallet
    from bot.nft.models import NFTAlert

    wallets  = WatchedWallet.objects.filter(
        telegram_user=telegram_user,
        chain__in=["eth", "arb", "base"],
    )
    activity = []

    for wallet in wallets:
        try:
            nft_txs = _get_nft_transfers(wallet.address, wallet.chain)
            for tx in nft_txs:
                tx_hash = tx.get("hash", "")
                # Skip already-alerted
                if NFTAlert.objects.filter(
                    telegram_user=telegram_user,
                    tx_hash=tx_hash,
                ).exists():
                    continue

                from_addr = tx.get("from", "").lower()
                direction = "sell" if from_addr == wallet.address.lower() else "buy"

                # Try to get collection info
                contract    = tx.get("contractAddress", "")
                token_name  = tx.get("tokenName", "?")
                token_id    = tx.get("tokenID", "")

                activity.append({
                    "wallet":     wallet,
                    "tx_hash":    tx_hash,
                    "direction":  direction,
                    "contract":   contract,
                    "token_name": token_name,
                    "token_id":   token_id,
                })
        except Exception as e:
            logger.debug("NFT activity check failed for %s: %s", wallet.address[:12], e)

    return activity


def _get_nft_transfers(address: str, chain: str) -> list[dict]:
    """Fetch ERC-721/1155 transfers via Etherscan tokennfttx."""
    from bot.blockchain.etherscan import _get

    data = _get(
        chain,
        {
            "module":  "account",
            "action":  "tokennfttx",
            "address": address,
            "sort":    "desc",
            "page":    1,
            "offset":  10,
        },
    )
    if data and isinstance(data.get("result"), list):
        return data["result"]
    return []


# ── Alert formatters ──────────────────────────────────────────────────────────

def format_floor_alert(collection, alert_data: dict) -> str:
    name        = he(collection.name or collection.slug)
    new_floor   = alert_data["new_floor"]
    prev_floor  = alert_data["prev_floor"]
    change_pct  = alert_data["change_pct"]
    floor_usd   = eth_to_usd(new_floor, "eth")
    usd_str     = f" ({format_usd(floor_usd)})" if floor_usd else ""

    if alert_data["type"] == "floor_drop":
        emoji = "📉"
        label = "Floor Price Drop"
        direction = f"↓ {abs(change_pct):.1f}%"
    else:
        emoji = "📈"
        label = "Floor Price Rise"
        direction = f"↑ {change_pct:.1f}%"

    return (
        f"{emoji} <b>NFT {label}</b>\n\n"
        f"Collection: <b>{name}</b>\n"
        f"Chain: {collection.chain.upper()}\n\n"
        f"Floor: <b>{new_floor:.3f} ETH</b>{usd_str}\n"
        f"Was: {prev_floor:.3f} ETH\n"
        f"Change: <b>{direction}</b>\n\n"
        f'<a href="https://opensea.io/collection/{collection.slug}">View on OpenSea</a>'
    )


def format_volume_spike_alert(collection, alert_data: dict) -> str:
    name     = he(collection.name or collection.slug)
    mult     = alert_data["multiplier"]
    vol_1h   = alert_data["volume_1h"]
    vol_24h  = alert_data["volume_24h"]

    return (
        f"🔥 <b>NFT Volume Spike</b>\n\n"
        f"Collection: <b>{name}</b>\n"
        f"Chain: {collection.chain.upper()}\n\n"
        f"1h volume: <b>{vol_1h:.2f} ETH</b> ({mult:.1f}x normal)\n"
        f"24h volume: {vol_24h:.2f} ETH\n\n"
        f'<a href="https://opensea.io/collection/{collection.slug}">View on OpenSea</a>'
    )


def format_sweep_alert(collection, alert_data: dict) -> str:
    name        = he(collection.name or collection.slug)
    buyer_count = alert_data["buyer_count"]
    sale_count  = alert_data["sale_count"]
    total_vol   = alert_data["total_vol_eth"]

    return (
        f"🧹 <b>Collection Sweep Detected!</b>\n\n"
        f"Collection: <b>{name}</b>\n"
        f"Chain: {collection.chain.upper()}\n\n"
        f"Buyers (1h): <b>{buyer_count} wallets</b>\n"
        f"Sales (1h): {sale_count}\n"
        f"Volume (1h): <b>{total_vol:.2f} ETH</b>\n\n"
        f'<a href="https://opensea.io/collection/{collection.slug}">View on OpenSea</a>'
    )


def format_whale_nft_alert(activity: dict) -> str:
    wallet    = activity["wallet"]
    direction = activity["direction"]
    token     = he(activity["token_name"])
    token_id  = he(activity["token_id"])
    tx_hash   = activity["tx_hash"]
    label     = he(wallet.label or f"{wallet.address[:10]}…")

    emoji     = "🖼 🟢" if direction == "buy" else "🖼 🔴"
    action    = "Bought" if direction == "buy" else "Sold"

    explorer  = {
        "eth":  "https://etherscan.io/tx",
        "arb":  "https://arbiscan.io/tx",
        "base": "https://basescan.org/tx",
    }.get(wallet.chain, "https://etherscan.io/tx")

    return (
        f"{emoji} <b>Whale NFT {action}</b>\n\n"
        f"Wallet: <b>{label}</b>\n"
        f"NFT: <b>{token}</b> #{token_id}\n"
        f"Chain: {wallet.chain.upper()}\n\n"
        f'<a href="{explorer}/{tx_hash}">View Transaction</a>'
    )