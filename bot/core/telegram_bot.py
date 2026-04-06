"""
Cryptocate Telegram Bot — command handlers with inline button menus.

All major actions are available as inline buttons AND slash commands.
Buttons use structured callback_data: "action:param1:param2"

parse_mode: HTML throughout — safer than MarkdownV2 for dynamic content.

References:
  https://docs.python-telegram-bot.org/en/stable/
  https://docs.djangoproject.com/en/5.2/topics/async/
"""

import logging
import secrets
from html import escape as he  # he() = html_escape — used on all dynamic values

import redis
from asgiref.sync import sync_to_async
from django.conf import settings
from telegram import InlineKeyboardButton as Btn
from telegram import InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

logger = logging.getLogger(__name__)
LINK_TOKEN_TTL = 3600
HTML = ParseMode.HTML


# ── Redis ──────────────────────────────────────────────────────────────────────

def _get_redis() -> redis.Redis:
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


# ── Registration link ──────────────────────────────────────────────────────────

def _reg_link(user) -> str:
    token = secrets.token_urlsafe(32)
    _get_redis().setex(f"reg_link:{token}", LINK_TOKEN_TTL, str(user.telegram_id))
    return f"{settings.WEBHOOK_URL}/accounts/register/?token={token}"



@sync_to_async
def _db_nft_collections(user) -> list:
    """Return all watched NFT collections for a user."""
    from bot.nfts.models import WatchedCollection
    return list(
        WatchedCollection.objects.filter(telegram_user=user)
        .values("id", "slug", "name", "chain", "floor_price_eth",
                "floor_drop_pct", "floor_rise_pct", "added_at")
        .order_by("added_at")
    )

@sync_to_async
def _db_add_nft_collection(user, slug: str, chain: str) -> tuple:
    """Add a watched NFT collection. Returns (collection_dict, created, error_str)."""
    from bot.nfts.models import WatchedCollection
    from bot.nfts.opensea import get_collection_info

    # Free plan: max 1 collection
    is_pro = user.is_pro()
    count  = WatchedCollection.objects.filter(telegram_user=user).count()
    if not is_pro and count >= 1:
        return None, False, "free_limit"
    if count >= 20:
        return None, False, "pro_limit"

    # Fetch collection name from OpenSea
    info = get_collection_info(slug) or {}
    name = info.get("name", slug)
    contract = info.get("contract_address", "")

    col, created = WatchedCollection.objects.get_or_create(
        telegram_user=user,
        slug=slug.lower(),
        chain=chain,
        defaults={"name": name, "contract_address": contract},
    )
    return {"slug": col.slug, "name": col.name, "chain": col.chain}, created, ""

@sync_to_async
def _db_remove_nft_collection(user, slug: str, chain: str) -> int:
    from bot.nfts.models import WatchedCollection
    return WatchedCollection.objects.filter(
        telegram_user=user, slug=slug.lower(), chain=chain
    ).delete()[0]

@sync_to_async
def _db_nft_collection_count(user) -> int:
    from bot.nfts.models import WatchedCollection
    return WatchedCollection.objects.filter(telegram_user=user).count()

# ── Keyboard builders ──────────────────────────────────────────────────────────

def _kb_register(user) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[Btn("🚀 Register to start", url=_reg_link(user))]])


def _kb_complete_reg(user) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[Btn("🚀 Complete registration", url=_reg_link(user))]])


def _kb_main(is_pro: bool) -> InlineKeyboardMarkup:
    rows = [
        [Btn("👛 My Wallets", callback_data="cmd:list"),
         Btn("📊 Status",     callback_data="cmd:status")],
        [Btn("➕ Add Wallet",  callback_data="cmd:add_prompt"),
         Btn("💰 Balance",    callback_data="cmd:balance_prompt")],
    ]
    if is_pro:
        rows.append([
            Btn("📰 Digest",    callback_data="cmd:digest"),
            Btn("📈 Scores",   callback_data="cmd:score"),
        ])
        rows.append([
            Btn("🐋 Whales",   callback_data="cmd:whales"),
            Btn("🐸 Memecoins",     callback_data="cmd:meme_menu"),
        ])
        rows.append([Btn("🖼 NFT Tracker", callback_data="nft:list")])
    else:
        rows.append([
            Btn("🐸 Meme Check", callback_data="cmd:meme_menu"),
            Btn("⭐ Upgrade to Pro", callback_data="cmd:subscribe"),
        ])
    rows.append([Btn("❓ Help", callback_data="cmd:help_text")])
    return InlineKeyboardMarkup(rows)


def _kb_wallets(wallets: list, is_pro: bool) -> InlineKeyboardMarkup:
    """One row per wallet with a Remove button, plus Add and Back."""
    rows = []
    for w in wallets:
        short = he(w["address"][:10]) + "…"
        label = f" ({he(w['label'])})" if w["label"] else ""
        rows.append([
            Btn(f"🗑 {w['chain'].upper()}: {short}{label}",
                callback_data=f"wallet:remove_confirm:{w['address']}:{w['chain']}"),
        ])
    rows.append([
        Btn("➕ Add Wallet", callback_data="cmd:add_prompt"),
        Btn("🔙 Menu",       callback_data="cmd:menu"),
    ])
    return InlineKeyboardMarkup(rows)


def _kb_confirm_remove(address: str, chain: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        Btn("✅ Yes, remove", callback_data=f"wallet:remove:{address}:{chain}"),
        Btn("❌ Cancel",      callback_data="cmd:list"),
    ]])



def _kb_nft(collections: list, is_pro: bool) -> InlineKeyboardMarkup:
    rows = []
    for col in collections:
        name  = col.get("name") or col.get("slug", "?")
        chain = col.get("chain", "eth").upper()
        slug  = col.get("slug", "")
        rows.append([
            Btn(f"🖼 {name[:20]} [{chain}]", callback_data=f"nft:detail:{slug}:{col['chain']}"),
            Btn("🗑", callback_data=f"nft:remove_confirm:{slug}:{col['chain']}"),
        ])
    rows.append([Btn("➕ Add Collection", callback_data="nft:add_prompt")])
    if not is_pro:
        rows.append([Btn("⭐ Pro: Unlimited Collections", callback_data="cmd:subscribe")])
    rows.append([Btn("🔙 Menu", callback_data="cmd:menu")])
    return InlineKeyboardMarkup(rows)

def _kb_nft_confirm_remove(slug: str, chain: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        Btn("✅ Yes, remove", callback_data=f"nft:remove:{slug}:{chain}"),
        Btn("❌ Cancel",      callback_data="nft:list"),
    ]])

def _kb_subscribe(checkout_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [Btn("💳 Subscribe — $29/mo", url=checkout_url)],
        [Btn("🔙 Menu", callback_data="cmd:menu")],
    ])


def _kb_meme() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [Btn("🔍 Rug Check",    callback_data="meme:check_prompt"),
         Btn("🔭 Scan Pairs",   callback_data="meme:scan")],
        [Btn("🔥 Trending",     callback_data="meme:trending"),
         Btn("🔙 Menu",         callback_data="cmd:menu")],
    ])


def _kb_digest(enabled: bool) -> InlineKeyboardMarkup:
    toggle_label = "🔕 Disable" if enabled else "🔔 Enable"
    toggle_cb    = "digest:off" if enabled else "digest:on"
    return InlineKeyboardMarkup([
        [Btn("⏰ Set 6am",  callback_data="digest:hour:6"),
         Btn("⏰ Set 8am",  callback_data="digest:hour:8"),
         Btn("⏰ Set 12pm", callback_data="digest:hour:12")],
        [Btn("⏰ Set 6pm",  callback_data="digest:hour:18"),
         Btn("⏰ Set 9pm",  callback_data="digest:hour:21"),
         Btn(toggle_label,  callback_data=toggle_cb)],
        [Btn("🔙 Menu",     callback_data="cmd:menu")],
    ])


def _kb_back_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[Btn("🔙 Menu", callback_data="cmd:menu")]])


def _kb_pro_gate() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [Btn("⭐ Upgrade to Pro", callback_data="cmd:subscribe")],
        [Btn("🔙 Menu",           callback_data="cmd:menu")],
    ])


# ── sync_to_async DB helpers ───────────────────────────────────────────────────

@sync_to_async
def _db_get_or_create(telegram_id, username, first_name):
    from bot.core.models import TelegramUser
    return TelegramUser.objects.get_or_create(
        telegram_id=telegram_id,
        defaults={"username": username, "first_name": first_name},
    )

@sync_to_async
def _db_reg_complete(user) -> bool:
    return user.registration_complete

@sync_to_async
def _db_is_pro(user) -> bool:
    return user.is_pro()

@sync_to_async
def _db_wallet_count(user) -> int:
    return user.wallets.count()

@sync_to_async
def _db_wallet_limit(user) -> int:
    return user.wallet_limit()

@sync_to_async
def _db_threshold(user) -> float:
    return user.alert_threshold_eth()

@sync_to_async
def _db_email(user):
    return user.verified_email

@sync_to_async
def _db_attrs(user) -> dict:
    return {
        "telegram_id":        user.telegram_id,
        "username":           user.username,
        "first_name":         user.first_name,
        "plan":               user.plan,
        "subscription_ends_at": user.subscription_ends_at,
        "digest_enabled":     user.digest_enabled,
        "digest_hour":        user.digest_hour,
    }

@sync_to_async
def _db_wallets(user) -> list:
    out = []
    for w in user.wallets.all().order_by("chain", "added_at"):
        score = None
        try:
            score = w.score.score
        except Exception:
            pass
        out.append({
            "address":   w.address,
            "chain":     w.chain,
            "label":     w.label,
            "threshold": w.effective_threshold(),
            "score":     score,
        })
    return out

@sync_to_async
def _db_add_wallet(user, address, chain, label):
    from bot.core.models import WatchedWallet
    w, created = WatchedWallet.objects.get_or_create(
        telegram_user=user,
        address=address.lower(),
        chain=chain,
        defaults={"label": label},
    )
    return {"threshold": w.effective_threshold()}, created

@sync_to_async
def _db_remove_wallet(user, address, chain) -> int:
    qs = user.wallets.filter(address=address.lower())
    if chain:
        qs = qs.filter(chain=chain)
    n = qs.count()
    qs.delete()
    return n

@sync_to_async
def _db_set_threshold(user, address, threshold) -> bool:
    from bot.core.models import WatchedWallet
    try:
        w = user.wallets.get(address=address.lower())
        w.custom_threshold_eth = threshold
        w.save(update_fields=["custom_threshold_eth"])
        return True
    except WatchedWallet.DoesNotExist:
        return False

@sync_to_async
def _db_set_digest(user, enabled, hour):
    fields = []
    if enabled is not None:
        user.digest_enabled = enabled
        fields.append("digest_enabled")
    if hour is not None:
        user.digest_hour = hour
        fields.append("digest_hour")
    if fields:
        user.save(update_fields=fields)

@sync_to_async
def _db_scores(user) -> list:
    out = []
    for w in user.wallets.select_related("score").all():
        try:
            s = w.score
            out.append({"address": w.address, "chain": w.chain,
                        "score": s.score, "win_rate": s.win_rate,
                        "total_trades": s.total_trades})
        except Exception:
            out.append({"address": w.address, "chain": w.chain,
                        "score": None, "win_rate": None, "total_trades": None})
    return out

@sync_to_async
def _db_add_deployer(user, address):
    from bot.memecoin.deployer.tracker import add_deployer_wallet
    add_deployer_wallet(user, address)

@sync_to_async
def _db_directory() -> str:
    from bot.directory.helpers import get_directory_summary
    return get_directory_summary()

@sync_to_async
def _db_checkout(user) -> str:
    from bot.payments.paddle import create_checkout_url
    return create_checkout_url(user)

@sync_to_async
def _db_rugcheck(token_address) -> str:
    from bot.memecoin.rugcheck.checker import check_token
    return check_token(token_address)

@sync_to_async
def _db_new_pairs() -> list:
    from bot.memecoin.scanner.dexscreener import get_new_pairs
    return get_new_pairs(limit=5)

@sync_to_async
def _db_trending() -> list:
    from bot.memecoin.momentum.alerts import get_trending_tokens
    return get_trending_tokens()

@sync_to_async
def _db_eth_balance(address, chain) -> float:
    from bot.blockchain.etherscan import _get
    data = _get(chain, {"module": "account", "action": "balance",
                        "address": address, "tag": "latest"})
    if data and data.get("result"):
        try:
            return int(data["result"]) / 1e18
        except (ValueError, TypeError):
            pass
    return 0.0

@sync_to_async
def _db_price(coin_id):
    from bot.prices.coingecko import get_price_usd
    return get_price_usd(coin_id)


# ── Shared response builders ───────────────────────────────────────────────────

async def _get_user(update: Update):
    tg = update.effective_user
    return await _db_get_or_create(tg.id, tg.username or "", tg.first_name or "")


async def _reply(update: Update, text: str, keyboard=None):
    """Reply to either a message or a callback query."""
    msg = update.message or (update.callback_query and update.callback_query.message)
    if msg:
        await msg.reply_text(text, parse_mode=HTML, reply_markup=keyboard)


async def _edit(update: Update, text: str, keyboard=None):
    """Edit the existing message (callback context)."""
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text, parse_mode=HTML, reply_markup=keyboard
            )
        except Exception:
            await _reply(update, text, keyboard)
    else:
        await _reply(update, text, keyboard)


async def _require_reg(update: Update, user) -> bool:
    if await _db_reg_complete(user):
        return False
    msg = update.message or (update.callback_query and update.callback_query.message)
    if msg:
        await msg.reply_text(
            "⚠️ Please complete your registration first.\n"
            "Tap below — takes under 60 seconds.",
            parse_mode=HTML,
            reply_markup=_kb_complete_reg(user),
        )
    return True


def _badge(is_pro: bool) -> str:
    return "⭐ <b>PRO</b>" if is_pro else "🆓 <b>FREE</b>"


# ── Welcome/menu screen (shared by /start, /menu, and "Menu" button) ──────────

async def _show_menu(update: Update, user, edit: bool = False):
    """Render the main menu. edit=True updates an existing message."""
    is_pro    = await _db_is_pro(user)
    wcount    = await _db_wallet_count(user)
    wlimit    = await _db_wallet_limit(user)
    threshold = await _db_threshold(user)
    email     = await _db_email(user)
    attrs     = await _db_attrs(user)
    name      = he(attrs["first_name"] or attrs["username"] or "Whale")
    chains    = "ETH · ARB · BASE · BSC · SOL" if is_pro else "ETH only"

    text = (
        f"🐋 <b>Cryptocate Bot</b> — {_badge(is_pro)}\n\n"
        f"👤 {name}\n"
        f"📧 {he(email or 'not linked')}\n"
        f"👛 Wallets: {wcount}/{wlimit}\n"
        f"⛓ Chains: {chains}\n"
        f"📊 Threshold: {threshold} ETH\n"
    )

    kb = _kb_main(is_pro)
    if edit:
        await _edit(update, text, kb)
    else:
        await _reply(update, text, kb)


# ── /start ─────────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, _ = await _get_user(update)

    if not await _db_reg_complete(user):
        await _reply(
            update,
            "👋 <b>Welcome to Cryptocate Bot!</b>\n\n"
            "Before you can track wallets, create your free account.\n"
            "It takes under 60 seconds — email or Google.\n\n"
            "Your account keeps your wallets, alerts, and subscription "
            "safe if you ever switch Telegram accounts.",
            _kb_register(user),
        )
        return

    await _show_menu(update, user)


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, _ = await _get_user(update)
    if await _require_reg(update, user):
        return
    await _show_menu(update, user)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, context)


# ── /status ────────────────────────────────────────────────────────────────────

async def _show_status(update: Update, user, edit=False):
    is_pro    = await _db_is_pro(user)
    wcount    = await _db_wallet_count(user)
    wlimit    = await _db_wallet_limit(user)
    threshold = await _db_threshold(user)
    email     = await _db_email(user)
    attrs     = await _db_attrs(user)
    ends_at   = attrs["subscription_ends_at"]
    sub_line  = f"\n🔄 Renews: {ends_at.strftime('%Y-%m-%d')}" if is_pro and ends_at else ""

    text = (
        f"📊 <b>Account Status</b>\n\n"
        f"Plan: {_badge(is_pro)}{sub_line}\n"
        f"Wallets: {wcount}/{wlimit}\n"
        f"Threshold: {threshold} ETH\n"
        f"{'📧 ' + he(email) + ' ✅' if email else '📧 Not linked'}\n"
        f"Telegram ID: <code>{attrs['telegram_id']}</code>"
    )
    kb = InlineKeyboardMarkup([[
        Btn("🔙 Menu", callback_data="cmd:menu"),
        Btn("⭐ Upgrade", callback_data="cmd:subscribe") if not is_pro else Btn("📋 Wallets", callback_data="cmd:list"),
    ]])
    if edit:
        await _edit(update, text, kb)
    else:
        await _reply(update, text, kb)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, _ = await _get_user(update)
    if await _require_reg(update, user):
        return
    await _show_status(update, user)


# ── /subscribe ─────────────────────────────────────────────────────────────────

async def _show_subscribe(update: Update, user, edit=False):
    from bot.payments.paddle import NeedsRegistration
    if await _db_is_pro(user):
        text = "⭐ You're already on the <b>Pro plan</b>!"
        kb   = _kb_back_menu()
        if edit:
            await _edit(update, text, kb)
        else:
            await _reply(update, text, kb)
        return

    try:
        url   = await _db_checkout(user)
        email = await _db_email(user)
        text = (
            f"🚀 <b>Upgrade to Cryptocate Pro</b>\n\n"
            f"📧 Billing email: <code>{he(email or '')}</code>\n\n"
            "• 10 wallets · All 5 chains\n"
            "• 1 ETH threshold\n"
            "• ERC-20 alerts &gt;$10K\n"
            "• Daily digest · Copy-trade signals\n"
            "• Full memecoin suite\n\n"
            "<b>$29/month</b> — cancel any time."
        )
        kb = _kb_subscribe(url)
        if edit:
            await _edit(update, text, kb)
        else:
            await _reply(update, text, kb)
    except NeedsRegistration:
        await _reply(update,
            "⚠️ Please complete your registration before subscribing.",
            _kb_complete_reg(user))


async def cmd_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, _ = await _get_user(update)
    if await _require_reg(update, user):
        return
    await _show_subscribe(update, user)


# ── /add ───────────────────────────────────────────────────────────────────────

async def _show_add_prompt(update: Update, user, edit=False):
    is_pro = await _db_is_pro(user)
    chains = "eth, arb, base, bsc, sol" if is_pro else "eth only"
    text = (
        f"➕ <b>Add a Wallet</b>\n\n"
        f"Send a command:\n"
        f"<code>/add &lt;address&gt; [chain] [label]</code>\n\n"
        f"Examples:\n"
        f"<code>/add 0xd8dA6BF26... eth MyWhale</code>\n"
        f"<code>/add 9WzDXwBb... sol</code>\n\n"
        f"Available chains: {he(chains)}"
    )
    kb = _kb_back_menu()
    if edit:
        await _edit(update, text, kb)
    else:
        await _reply(update, text, kb)


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, _ = await _get_user(update)
    if await _require_reg(update, user):
        return

    if not context.args:
        await _show_add_prompt(update, user)
        return

    address = context.args[0].strip()
    chain   = context.args[1].lower() if len(context.args) > 1 else "eth"
    label   = " ".join(context.args[2:]) if len(context.args) > 2 else ""
    is_pro  = await _db_is_pro(user)
    valid   = ["eth", "arb", "base", "bsc", "sol"] if is_pro else ["eth"]

    if chain not in valid:
        await _reply(update,
            f"❌ Chain <code>{he(chain)}</code> not available on your plan.\n"
            f"Upgrade to Pro for Arbitrum, Base, BSC, and Solana.",
            _kb_pro_gate() if not is_pro else _kb_back_menu())
        return

    wcount = await _db_wallet_count(user)
    wlimit = await _db_wallet_limit(user)
    if wcount >= wlimit:
        await _reply(update,
            f"❌ Wallet limit reached ({wlimit} wallets).\n"
            f"Remove one with /remove, or upgrade to Pro for 10 wallets.",
            _kb_pro_gate() if not is_pro else _kb_back_menu())
        return

    data, created = await _db_add_wallet(user, address, chain, label)
    if not created:
        await _reply(update,
            f"⚠️ <code>{he(address[:12])}…</code> is already watched on {chain.upper()}.",
            InlineKeyboardMarkup([[Btn("📋 My Wallets", callback_data="cmd:list"),
                                   Btn("🔙 Menu", callback_data="cmd:menu")]]))
        return

    label_text = f" ({he(label)})" if label else ""
    await _reply(update,
        f"✅ Now watching <code>{he(address[:12])}…</code> on <b>{chain.upper()}</b>{label_text}\n"
        f"Threshold: {data['threshold']} ETH  ·  Wallets: {wcount+1}/{wlimit}",
        InlineKeyboardMarkup([[Btn("📋 My Wallets", callback_data="cmd:list"),
                               Btn("🔙 Menu",       callback_data="cmd:menu")]]))


# ── /list ──────────────────────────────────────────────────────────────────────

async def _show_list(update: Update, user, edit=False):
    wallets = await _db_wallets(user)
    wlimit  = await _db_wallet_limit(user)

    if not wallets:
        text = "No wallets being watched yet.\nTap <b>Add Wallet</b> to start."
        kb   = InlineKeyboardMarkup([[Btn("➕ Add Wallet", callback_data="cmd:add_prompt"),
                                      Btn("🔙 Menu",      callback_data="cmd:menu")]])
        if edit: await _edit(update, text, kb)
        else:    await _reply(update, text, kb)
        return

    lines = [f"👛 <b>Watched Wallets</b> ({len(wallets)}/{wlimit})\n"]
    for i, w in enumerate(wallets, 1):
        label = f" — {he(w['label'])}" if w["label"] else ""
        score = f" [{w['score']:.1f}/10]" if w["score"] is not None else ""
        lines.append(
            f"{i}. <code>{he(w['address'][:12])}…</code> <b>{w['chain'].upper()}</b>{label}{score}\n"
            f"   Threshold: {w['threshold']} ETH"
        )

    text = "\n".join(lines)
    kb   = _kb_wallets(wallets, await _db_is_pro(user))
    if edit: await _edit(update, text, kb)
    else:    await _reply(update, text, kb)


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, _ = await _get_user(update)
    if await _require_reg(update, user):
        return
    await _show_list(update, user)


# ── /remove ────────────────────────────────────────────────────────────────────

async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, _ = await _get_user(update)
    if await _require_reg(update, user):
        return

    if not context.args:
        await _show_list(update, user)  # show wallet list with remove buttons
        return

    address = context.args[0].strip()
    chain   = context.args[1].lower() if len(context.args) > 1 else None
    count   = await _db_remove_wallet(user, address, chain)

    if count == 0:
        await _reply(update,
            f"❌ No wallet matching <code>{he(address[:12])}…</code> found.",
            _kb_back_menu())
    else:
        await _reply(update,
            f"✅ Removed <code>{he(address[:12])}…</code>.",
            InlineKeyboardMarkup([[Btn("📋 My Wallets", callback_data="cmd:list"),
                                   Btn("🔙 Menu",       callback_data="cmd:menu")]]))


# ── /balance ───────────────────────────────────────────────────────────────────

async def _show_balance_prompt(update: Update, user, edit=False):
    text = (
        "💰 <b>Check Balance</b>\n\n"
        "<code>/balance &lt;address&gt; [chain]</code>\n\n"
        "Example:\n"
        "<code>/balance 0xd8dA6BF26... eth</code>"
    )
    kb = _kb_back_menu()
    if edit: await _edit(update, text, kb)
    else:    await _reply(update, text, kb)


async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, _ = await _get_user(update)
    if await _require_reg(update, user):
        return

    if not context.args:
        await _show_balance_prompt(update, user)
        return

    address = context.args[0].strip()
    chain   = context.args[1].lower() if len(context.args) > 1 else "eth"

    await _reply(update,
        f"🔍 Fetching balance for <code>{he(address[:12])}…</code> on <b>{chain.upper()}</b>…")

    try:
        balance_eth = await _db_eth_balance(address, chain)
        price       = await _db_price("ethereum")
        usd         = f" (${balance_eth * price:,.2f})" if price else ""
        await _reply(update,
            f"💰 <b>{balance_eth:.4f} ETH</b>{he(usd)}\n"
            f"<code>{he(address[:12])}…</code> · {chain.upper()}",
            _kb_back_menu())
    except Exception as e:
        logger.error("Balance check failed %s: %s", address, e)
        await _reply(update, "❌ Failed to fetch balance. Try again later.", _kb_back_menu())


# ── /threshold ─────────────────────────────────────────────────────────────────

async def cmd_threshold(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, _ = await _get_user(update)
    if await _require_reg(update, user):
        return
    if not await _db_is_pro(user):
        await _reply(update, "⭐ Custom thresholds are a <b>Pro</b> feature.", _kb_pro_gate())
        return
    if not context.args or len(context.args) < 2:
        await _reply(update,
            "Usage: <code>/threshold &lt;address&gt; &lt;eth_value&gt;</code>\n"
            "Example: <code>/threshold 0xd8dA6B… 0.5</code>",
            _kb_back_menu())
        return

    address = context.args[0].strip()
    try:
        threshold = float(context.args[1])
    except ValueError:
        await _reply(update, "❌ Invalid value. Use a number e.g. <code>2.5</code>", _kb_back_menu())
        return

    found = await _db_set_threshold(user, address, threshold)
    if found:
        await _reply(update,
            f"✅ Threshold set to <b>{threshold} ETH</b> for <code>{he(address[:12])}…</code>",
            InlineKeyboardMarkup([[Btn("📋 Wallets", callback_data="cmd:list"),
                                   Btn("🔙 Menu",    callback_data="cmd:menu")]]))
    else:
        await _reply(update,
            f"❌ Wallet <code>{he(address[:12])}…</code> not found.", _kb_back_menu())


# ── /tokens ────────────────────────────────────────────────────────────────────

async def cmd_tokens(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, _ = await _get_user(update)
    if await _require_reg(update, user):
        return
    if not await _db_is_pro(user):
        await _reply(update, "⭐ ERC-20 token alerts are a <b>Pro</b> feature.", _kb_pro_gate())
        return
    await _reply(update,
        "🪙 <b>ERC-20 Token Alerts</b>\n\n"
        "Alerts fire when your wallets move tokens worth ≥ $10,000.\n"
        "Enabled automatically for all Pro wallets.",
        _kb_back_menu())


# ── /digest ────────────────────────────────────────────────────────────────────

async def _show_digest(update: Update, user, edit=False):
    enabled, hour = await (sync_to_async(lambda u: (u.digest_enabled, u.digest_hour))(user))
    text = (
        f"📰 <b>Daily Digest</b>\n\n"
        f"Status: {'✅ Enabled' if enabled else '❌ Disabled'}\n"
        f"Send time: {hour:02d}:00 UTC\n\n"
        "Tap a button to change the send time or toggle on/off."
    )
    kb = _kb_digest(enabled)
    if edit: await _edit(update, text, kb)
    else:    await _reply(update, text, kb)


async def cmd_digest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, _ = await _get_user(update)
    if await _require_reg(update, user):
        return
    if not await _db_is_pro(user):
        await _reply(update, "⭐ Daily digests are a <b>Pro</b> feature.", _kb_pro_gate())
        return

    if context.args:
        arg = context.args[0].lower()
        if arg == "off":
            await _db_set_digest(user, enabled=False, hour=None)
            await _reply(update, "✅ Daily digest disabled.", _kb_back_menu())
            return
        if arg.isdigit() and 0 <= int(arg) <= 23:
            await _db_set_digest(user, enabled=True, hour=int(arg))
            await _reply(update, f"✅ Daily digest set to {int(arg):02d}:00 UTC.", _kb_back_menu())
            return

    await _show_digest(update, user)


# ── /score ─────────────────────────────────────────────────────────────────────

async def _show_scores(update: Update, user, edit=False):
    scores = await _db_scores(user)
    if not scores:
        text = "No wallets watched yet."
        kb   = InlineKeyboardMarkup([[Btn("➕ Add Wallet", callback_data="cmd:add_prompt"),
                                      Btn("🔙 Menu",      callback_data="cmd:menu")]])
        if edit: await _edit(update, text, kb)
        else:    await _reply(update, text, kb)
        return

    lines = ["📊 <b>Wallet Profitability Scores</b>\n"]
    for s in scores:
        if s["score"] is not None:
            lines.append(
                f"<code>{he(s['address'][:12])}…</code> {s['chain'].upper()}\n"
                f"  <b>{s['score']:.1f}/10</b> · win rate {s['win_rate']:.0%} · {s['total_trades']} trades"
            )
        else:
            lines.append(f"<code>{he(s['address'][:12])}…</code> {s['chain'].upper()}\n  <i>pending</i>")

    text = "\n".join(lines)
    kb   = _kb_back_menu()
    if edit: await _edit(update, text, kb)
    else:    await _reply(update, text, kb)


async def cmd_score(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, _ = await _get_user(update)
    if await _require_reg(update, user):
        return
    if not await _db_is_pro(user):
        await _reply(update, "⭐ Wallet scores are a <b>Pro</b> feature.", _kb_pro_gate())
        return
    await _show_scores(update, user)


# ── /whales ────────────────────────────────────────────────────────────────────

async def cmd_whales(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, _ = await _get_user(update)
    if await _require_reg(update, user):
        return
    if not await _db_is_pro(user):
        await _reply(update, "⭐ The Whale Directory is a <b>Pro</b> feature.", _kb_pro_gate())
        return
    summary = await _db_directory()
    await _reply(update, summary, _kb_back_menu())


async def cmd_watch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_add(update, context)


# ── /meme ──────────────────────────────────────────────────────────────────────

async def _show_meme_menu(update: Update, user, edit=False):
    is_pro = await _db_is_pro(user)
    text = (
        "🐸 <b>Memecoin Suite</b>\n\n"
        + ("• Rug Check — analyse any token\n"
           "• Scan Pairs — new pairs right now\n"
           "• Trending — top tokens by volume\n\n"
           "Free plan: 5 rug checks/hour\n"
           "Pro: unlimited + scan + trending"
           if not is_pro else
           "• Rug Check — unlimited\n"
           "• Scan Pairs — new pairs right now\n"
           "• Trending — top tokens by volume\n\n"
           "Use the buttons below or type:\n"
           "<code>/meme check &lt;address&gt;</code>")
    )
    kb = _kb_meme()
    if edit: await _edit(update, text, kb)
    else:    await _reply(update, text, kb)


async def cmd_meme(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, _ = await _get_user(update)
    if await _require_reg(update, user):
        return

    if not context.args:
        await _show_meme_menu(update, user)
        return

    sub = context.args[0].lower()
    if sub == "check":
        if len(context.args) < 2:
            await _reply(update,
                "Usage: <code>/meme check &lt;token_address&gt;</code>",
                _kb_back_menu())
            return
        await _do_rug_check(update, user, context.args[1])
    elif sub in ("scan", "trending"):
        if not await _db_is_pro(user):
            await _reply(update,
                f"⭐ <code>/meme {he(sub)}</code> is a <b>Pro</b> feature.", _kb_pro_gate())
            return
        if sub == "scan":
            await _do_meme_scan(update)
        else:
            await _do_meme_trending(update)
    else:
        await _show_meme_menu(update, user)


async def _do_rug_check(update: Update, user, token_address: str) -> None:
    r      = _get_redis()
    is_pro = await _db_is_pro(user)
    attrs  = await _db_attrs(user)

    if not is_pro:
        key   = f"meme_check_rate:{attrs['telegram_id']}"
        count = r.incr(key)
        if count == 1:
            r.expire(key, 3600)
        if count > 5:
            ttl = r.ttl(key)
            await _reply(update,
                f"⏳ Rate limit reached (5/hour). Try again in {ttl // 60} min.",
                InlineKeyboardMarkup([[Btn("⭐ Upgrade for unlimited", callback_data="cmd:subscribe"),
                                       Btn("🔙 Menu", callback_data="cmd:menu")]]))
            return

    await _reply(update, f"🔍 Running rug check on <code>{he(token_address[:12])}…</code>…")
    try:
        result = await _db_rugcheck(token_address)
        await _reply(update, result, _kb_back_menu())
    except Exception as e:
        logger.error("Rug check failed %s: %s", token_address, e)
        await _reply(update, "❌ Rug check failed. Try again later.", _kb_back_menu())


async def _do_meme_scan(update: Update) -> None:
    try:
        pairs = await _db_new_pairs()
        if not pairs:
            await _reply(update, "No new pairs found right now.", _kb_back_menu())
            return
        lines = ["🔭 <b>New Meme Pairs</b>\n"]
        for p in pairs:
            sym = he(p.get("baseToken", {}).get("symbol", "?"))
            liq = p.get("liquidity", {}).get("usd", 0)
            lines.append(f"• <b>{sym}</b> — Liq: ${liq:,.0f}")
        await _reply(update, "\n".join(lines), _kb_back_menu())
    except Exception as e:
        logger.error("Meme scan failed: %s", e)
        await _reply(update, "❌ Scan failed.", _kb_back_menu())


async def _do_meme_trending(update: Update) -> None:
    try:
        tokens = await _db_trending()
        if not tokens:
            await _reply(update, "No trending tokens right now.", _kb_back_menu())
            return
        lines = ["🔥 <b>Trending Meme Tokens</b>\n"]
        for t in tokens[:5]:
            lines.append(
                f"• <b>{he(t.get('symbol','?'))}</b> — "
                f"Vol 1h: ${t.get('volume_1h',0):,.0f}"
            )
        await _reply(update, "\n".join(lines), _kb_back_menu())
    except Exception as e:
        logger.error("Meme trending failed: %s", e)
        await _reply(update, "❌ Failed to fetch trending tokens.", _kb_back_menu())



# ── /nft ───────────────────────────────────────────────────────────────────────

async def _show_nft_list(update: Update, user, edit=False):
    """Show the user's watched NFT collections with action buttons."""
    collections = await _db_nft_collections(user)
    is_pro      = await _db_is_pro(user)
    limit       = "unlimited" if is_pro else "1"

    if not collections:
        pro_features = (
            "• Volume spike detection\n"
            "• Collection sweep alerts\n"
            "• Whale wallet NFT activity\n"
        ) if is_pro else "• Upgrade to Pro for sweeps, volume spikes &amp; more\n"
        text = (
            "🖼 <b>NFT Tracker</b>\n\n"
            "No collections being watched yet.\n\n"
            "<b>What you get:</b>\n"
            "• Floor price drop/rise alerts\n"
            + pro_features
            + "\nTap <b>Add Collection</b> to start.\n"
            "<i>Free plan: 1 collection · Pro: unlimited</i>"
        )
        kb = InlineKeyboardMarkup([
            [Btn("➕ Add Collection", callback_data="nft:add_prompt")],
            [Btn("⭐ Upgrade for more", callback_data="cmd:subscribe")] if not is_pro else [],
            [Btn("🔙 Menu", callback_data="cmd:menu")],
        ])
    else:
        lines = [f"🖼 <b>NFT Collections</b> ({len(collections)}/{limit})\n"]
        for col in collections:
            name  = he(col.get("name") or col.get("slug", "?"))
            chain = col.get("chain", "eth").upper()
            floor = col.get("floor_price_eth")
            floor_str = f" — Floor: {floor:.3f} ETH" if floor else ""
            lines.append(f"• <b>{name}</b> [{chain}]{floor_str}")
        text = "\n".join(lines)
        kb   = _kb_nft(collections, is_pro)

    if edit:
        await _edit(update, text, kb)
    else:
        await _reply(update, text, kb)


async def cmd_nft(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /nft                     — show watched collections
    /nft add <slug> [chain]  — watch a collection
    /nft remove <slug>       — stop watching
    """
    user, _ = await _get_user(update)
    if await _require_reg(update, user):
        return

    if not context.args:
        await _show_nft_list(update, user)
        return

    sub = context.args[0].lower()

    if sub == "add":
        if len(context.args) < 2:
            await _reply(update,
                "Usage: <code>/nft add &lt;opensea-slug&gt; [chain]</code>\n\n"
                "The slug is the collection name in the OpenSea URL.\n"
                "Example: <code>/nft add boredapeyachtclub eth</code>",
                _kb_back_menu())
            return
        slug  = context.args[1].lower().strip()
        chain = context.args[2].lower() if len(context.args) > 2 else "eth"
        await _do_nft_add(update, user, slug, chain)

    elif sub == "remove":
        if len(context.args) < 2:
            await _show_nft_list(update, user)
            return
        slug  = context.args[1].lower().strip()
        chain = context.args[2].lower() if len(context.args) > 2 else "eth"
        count = await _db_remove_nft_collection(user, slug, chain)
        if count:
            await _reply(update,
                f"✅ Removed <code>{he(slug)}</code> from your NFT watchlist.",
                InlineKeyboardMarkup([[Btn("🖼 My Collections", callback_data="nft:list"),
                                       Btn("🔙 Menu",           callback_data="cmd:menu")]]))
        else:
            await _reply(update, f"❌ Collection <code>{he(slug)}</code> not found.", _kb_back_menu())
    else:
        await _show_nft_list(update, user)


async def _do_nft_add(update: Update, user, slug: str, chain: str) -> None:
    """Add a collection to the watchlist."""
    is_pro = await _db_is_pro(user)
    valid_chains = ["eth", "base", "arb"] if is_pro else ["eth"]

    if chain not in valid_chains:
        await _reply(update,
            f"❌ Chain <code>{he(chain)}</code> not available.\n"
            f"Available: {', '.join(valid_chains)}",
            _kb_back_menu())
        return

    await _reply(update, f"🔍 Looking up <code>{he(slug)}</code>…")

    col_data, created, error = await _db_add_nft_collection(user, slug, chain)

    if error == "free_limit":
        await _reply(update,
            "❌ Free plan supports 1 NFT collection.\n"
            "Upgrade to Pro for unlimited collections.",
            _kb_pro_gate())
        return
    if error == "pro_limit":
        await _reply(update, "❌ Maximum 20 NFT collections reached.", _kb_back_menu())
        return
    if not col_data:
        await _reply(update,
            f"❌ Could not find collection <code>{he(slug)}</code> on OpenSea.\n"
            "Check the slug — it's the part after /collection/ in the OpenSea URL.",
            _kb_back_menu())
        return
    if not created:
        await _reply(update,
            f"⚠️ <b>{he(col_data['name'])}</b> is already in your watchlist.",
            InlineKeyboardMarkup([[Btn("🖼 My Collections", callback_data="nft:list"),
                                   Btn("🔙 Menu",           callback_data="cmd:menu")]]))
        return

    count = await _db_nft_collection_count(user)
    limit = "unlimited" if is_pro else "1"
    pro_lines = (
        "• Volume spikes (3x normal)\n"
        "• Sweep detected (5+ wallets buy in 1h)\n"
        "• Your whale wallets buy/sell NFTs\n"
    ) if is_pro else "• <i>Upgrade to Pro for sweeps &amp; volume spikes</i>\n"
    name_str = he(col_data['name'])
    chain_str = chain.upper()
    await _reply(update,
        f"\u2705 Now watching <b>{name_str}</b> [{chain_str}]\n\n"
        "You'll receive alerts when:\n"
        "• Floor drops \u2265 10% or rises \u2265 20%\n"
        + pro_lines
        + f"\nCollections: {count}/{limit}",
        InlineKeyboardMarkup([[Btn("\U0001f5bc My Collections", callback_data="nft:list"),
                               Btn("\U0001f519 Menu",           callback_data="cmd:menu")]]))

# ── /deployer ──────────────────────────────────────────────────────────────────

async def cmd_deployer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, _ = await _get_user(update)
    if await _require_reg(update, user):
        return
    if not await _db_is_pro(user):
        await _reply(update, "⭐ Deployer tracking is a <b>Pro</b> feature.", _kb_pro_gate())
        return
    if not context.args:
        await _reply(update,
            "Usage: <code>/deployer &lt;address&gt;</code>\n"
            "Tracks a token deployer wallet and alerts you when they launch a new token.",
            _kb_back_menu())
        return
    address = context.args[0].strip()
    try:
        await _db_add_deployer(user, address)
        await _reply(update,
            f"✅ Now tracking deployer <code>{he(address[:12])}…</code>\n"
            "You'll be alerted when they deploy a new token.",
            _kb_back_menu())
    except ValueError as e:
        await _reply(update, f"⚠️ {he(str(e))}", _kb_back_menu())
    except Exception as e:
        logger.error("Deployer add failed %s: %s", address, e)
        await _reply(update, "❌ Failed to add deployer wallet.", _kb_back_menu())


# ── Callback query handler ─────────────────────────────────────────────────────

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user, _ = await _get_user(update)
    data    = query.data

    # ── Navigation ────────────────────────────────────────────────────────────
    if data == "cmd:menu":
        if not await _db_reg_complete(user):
            await query.message.reply_text(
                "⚠️ Please complete registration first.",
                reply_markup=_kb_complete_reg(user),
            )
            return
        await _show_menu(update, user, edit=True)

    elif data == "cmd:list":
        if await _require_reg(update, user): return
        await _show_list(update, user, edit=True)

    elif data == "cmd:status":
        if await _require_reg(update, user): return
        await _show_status(update, user, edit=True)

    elif data == "cmd:subscribe":
        if await _require_reg(update, user): return
        await _show_subscribe(update, user, edit=True)

    elif data == "cmd:add_prompt":
        if await _require_reg(update, user): return
        await _show_add_prompt(update, user, edit=True)

    elif data == "cmd:balance_prompt":
        if await _require_reg(update, user): return
        await _show_balance_prompt(update, user, edit=True)

    elif data == "cmd:digest":
        if await _require_reg(update, user): return
        if not await _db_is_pro(user):
            await _edit(update, "⭐ Daily digests are a <b>Pro</b> feature.", _kb_pro_gate())
            return
        await _show_digest(update, user, edit=True)

    elif data == "cmd:score":
        if await _require_reg(update, user): return
        if not await _db_is_pro(user):
            await _edit(update, "⭐ Wallet scores are a <b>Pro</b> feature.", _kb_pro_gate())
            return
        await _show_scores(update, user, edit=True)

    elif data == "cmd:whales":
        if await _require_reg(update, user): return
        if not await _db_is_pro(user):
            await _edit(update, "⭐ Whale Directory is a <b>Pro</b> feature.", _kb_pro_gate())
            return
        summary = await _db_directory()
        await _edit(update, summary, _kb_back_menu())

    elif data == "cmd:meme_menu":
        if await _require_reg(update, user): return
        await _show_meme_menu(update, user, edit=True)

    elif data == "cmd:help_text":
        text = (
            "📖 <b>All Commands</b>\n\n"
            "<b>Basic</b>\n"
            "/start or /menu — Main menu\n"
            "/add — Watch a wallet\n"
            "/list — Your wallets\n"
            "/remove — Stop watching\n"
            "/balance — Check balance\n"
            "/status — Account info\n"
            "/subscribe — Upgrade to Pro\n\n"
            "<b>Pro Only</b>\n"
            "/threshold — Custom alert threshold\n"
            "/tokens — ERC-20 token alerts\n"
            "/digest — Daily digest settings\n"
            "/score — Wallet profit scores\n"
            "/whales — Whale directory\n"
            "/deployer — Track deployer wallets\n\n"
            "<b>Memecoin</b>\n"
            "/meme check — Rug check (5/hr free)\n"
            "/meme scan — New pairs (Pro)\n"
            "/meme trending — Trending (Pro)\n\n"
        "<b>NFT Tracking</b>\n"
        "/nft — NFT collections dashboard\n"
        "/nft add &lt;slug&gt; — Watch a collection\n"
        "/nft remove &lt;slug&gt; — Stop watching"
        )
        await _edit(update, text, _kb_back_menu())

    # ── Wallet actions ────────────────────────────────────────────────────────
    elif data.startswith("wallet:remove_confirm:"):
        _, _, address, chain = data.split(":", 3)
        await _edit(update,
            f"🗑 Remove <code>{he(address[:12])}…</code> ({chain.upper()})?\n\n"
            "This will stop all alerts for this wallet.",
            _kb_confirm_remove(address, chain))

    elif data.startswith("wallet:remove:"):
        _, _, address, chain = data.split(":", 3)
        count = await _db_remove_wallet(user, address, chain)
        if count:
            await _edit(update,
                f"✅ Removed <code>{he(address[:12])}…</code>.",
                InlineKeyboardMarkup([[Btn("📋 My Wallets", callback_data="cmd:list"),
                                       Btn("🔙 Menu",       callback_data="cmd:menu")]]))
        else:
            await _edit(update, "❌ Wallet not found.", _kb_back_menu())

    # ── Digest controls ───────────────────────────────────────────────────────
    elif data == "digest:on":
        await _db_set_digest(user, enabled=True, hour=None)
        await _show_digest(update, user, edit=True)

    elif data == "digest:off":
        await _db_set_digest(user, enabled=False, hour=None)
        await _show_digest(update, user, edit=True)

    elif data.startswith("digest:hour:"):
        hour = int(data.split(":")[-1])
        await _db_set_digest(user, enabled=True, hour=hour)
        await _show_digest(update, user, edit=True)


    # ── NFT actions ───────────────────────────────────────────────────────────
    elif data == "nft:list":
        if await _require_reg(update, user): return
        await _show_nft_list(update, user, edit=True)

    elif data == "nft:add_prompt":
        if await _require_reg(update, user): return
        is_pro = await _db_is_pro(user)
        await _edit(update,
            "🖼 <b>Add NFT Collection</b>\n\n"
            "Send the OpenSea collection slug — it's the part after\n"
            "<code>opensea.io/collection/<b>slug-goes-here</b></code>\n\n"
            "Example commands:\n"
            "<code>/nft add boredapeyachtclub eth</code>\n"
            "<code>/nft add azuki eth</code>\n"
            + ("<code>/nft add y00ts sol</code>\n" if is_pro else "")
            + "\n<i>Free plan: ETH only, 1 collection · Pro: ETH/BASE/ARB, unlimited</i>",
            _kb_back_menu())

    elif data.startswith("nft:remove_confirm:"):
        parts = data.split(":", 3)
        slug, chain = parts[2], parts[3]
        col_name = he(slug)
        await _edit(update,
            f"🗑 Remove <b>{col_name}</b> [{chain.upper()}] from your watchlist?",
            _kb_nft_confirm_remove(slug, chain))

    elif data.startswith("nft:remove:"):
        if await _require_reg(update, user): return
        parts = data.split(":", 3)
        slug, chain = parts[2], parts[3]
        count = await _db_remove_nft_collection(user, slug, chain)
        if count:
            await _edit(update,
                f"✅ Removed <code>{he(slug)}</code>.",
                InlineKeyboardMarkup([[Btn("🖼 Collections", callback_data="nft:list"),
                                       Btn("🔙 Menu",        callback_data="cmd:menu")]]))
        else:
            await _edit(update, "❌ Collection not found.", _kb_back_menu())

    elif data.startswith("nft:detail:"):
        if await _require_reg(update, user): return
        parts     = data.split(":", 3)
        slug, chain = parts[2], parts[3]
        collections = await _db_nft_collections(user)
        col = next((c for c in collections if c["slug"] == slug and c["chain"] == chain), None)
        if not col:
            await _edit(update, "❌ Collection not found.", _kb_back_menu())
            return
        name   = he(col.get("name") or slug)
        floor  = col.get("floor_price_eth")
        floor_str = f"\nFloor: <b>{floor:.3f} ETH</b>" if floor else ""
        text = (
            f"🖼 <b>{name}</b> [{chain.upper()}]{floor_str}\n\n"
            f"Floor drop alert: ≥ {col['floor_drop_pct']:.0f}%\n"
            f"Floor rise alert: ≥ {col['floor_rise_pct']:.0f}%\n\n"
            f'<a href="https://opensea.io/collection/{slug}">View on OpenSea</a>'
        )
        await _edit(update, text, InlineKeyboardMarkup([
            [Btn("🗑 Remove", callback_data=f"nft:remove_confirm:{slug}:{chain}"),
             Btn("🔙 Collections", callback_data="nft:list")],
        ]))

    # ── Meme actions ──────────────────────────────────────────────────────────
    elif data == "meme:check_prompt":
        await _edit(update,
            "🔍 <b>Rug Check</b>\n\n"
            "Send the token contract address:\n"
            "<code>/meme check &lt;token_address&gt;</code>",
            _kb_back_menu())

    elif data == "meme:scan":
        if not await _db_is_pro(user):
            await _edit(update, "⭐ Pair scanning is a <b>Pro</b> feature.", _kb_pro_gate())
            return
        await _do_meme_scan(update)

    elif data == "meme:trending":
        if not await _db_is_pro(user):
            await _edit(update, "⭐ Trending is a <b>Pro</b> feature.", _kb_pro_gate())
            return
        await _do_meme_trending(update)


# ── Application builder ────────────────────────────────────────────────────────

def build_application() -> Application:
    app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("menu",      cmd_menu))
    app.add_handler(CommandHandler("help",      cmd_help))
    app.add_handler(CommandHandler("status",    cmd_status))
    app.add_handler(CommandHandler("subscribe", cmd_subscribe))
    app.add_handler(CommandHandler("add",       cmd_add))
    app.add_handler(CommandHandler("list",      cmd_list))
    app.add_handler(CommandHandler("remove",    cmd_remove))
    app.add_handler(CommandHandler("balance",   cmd_balance))
    app.add_handler(CommandHandler("threshold", cmd_threshold))
    app.add_handler(CommandHandler("tokens",    cmd_tokens))
    app.add_handler(CommandHandler("digest",    cmd_digest))
    app.add_handler(CommandHandler("score",     cmd_score))
    app.add_handler(CommandHandler("whales",    cmd_whales))
    app.add_handler(CommandHandler("watch",     cmd_watch))
    app.add_handler(CommandHandler("meme",      cmd_meme))
    app.add_handler(CommandHandler("deployer",  cmd_deployer))
    app.add_handler(CommandHandler("nft",       cmd_nft))
    app.add_handler(CallbackQueryHandler(button_callback))

    return app