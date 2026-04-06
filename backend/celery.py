"""
Celery configuration for Cryptocate.
Reference: https://docs.celeryq.dev/en/stable/django/first-steps-with-django.html
"""

import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")

app = Celery("cryptocate")

# Use Django settings for all Celery config
app.config_from_object("django.conf:settings", namespace="CELERY")

# Explicitly list every module that contains @shared_task definitions.
#
# autodiscover_tasks() only searches for a file literally named "tasks.py"
# inside each package — it will NOT find tasks defined in other files such as
# bot/prices/coingecko.py. Every module with @shared_task must be listed here.
#
# Full list of modules containing @shared_task (verified with grep):
#   bot/core/tasks.py
#   bot/digest/tasks.py
#   bot/dormant/tasks.py
#   bot/memecoin/deployer/tasks.py
#   bot/memecoin/scanner/tasks.py
#   bot/memecoin/tasks.py
#   bot/prices/coingecko.py   ← NOT tasks.py — must be listed by full module path
#   bot/scoring/tasks.py
app.autodiscover_tasks([
    "bot.core",
    "bot.digest",
    "bot.dormant",
    "bot.scoring",
    "bot.memecoin",
    "bot.memecoin.scanner",
    "bot.memecoin.deployer",
    "bot.nft",
])

# warm_price_cache lives in coingecko.py, not tasks.py, so autodiscover
# won't find it. Register the module explicitly by its full dotted path.
app.autodiscover_tasks(["bot.prices.coingecko"], force=True)

# ── Beat schedule ────────────────────────────────────────────────────────────
# https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html
app.conf.beat_schedule = {
    "poll_all_wallets": {
        "task": "bot.core.tasks.poll_all_wallets",
        "schedule": 120.0,
    },
    "warm_price_cache": {
        "task": "bot.prices.coingecko.warm_price_cache",
        "schedule": 600.0,  # 10 minutes — 4,320 calls/month within 10K cap
    },
    "send_daily_digests": {
        "task": "bot.digest.tasks.send_daily_digests",
        "schedule": 3600.0,
    },
    "score_all_wallets": {
        "task": "bot.scoring.tasks.score_all_wallets",
        "schedule": crontab(hour=0, minute=0, day_of_week="sunday"),
    },
    "reset_dormant_flags": {
        "task": "bot.dormant.tasks.reset_dormant_flags",
        "schedule": crontab(hour=1, minute=0, day_of_week="sunday"),
    },
    "scan_new_meme_pairs": {
        "task": "bot.memecoin.scanner.tasks.scan_new_meme_pairs",
        "schedule": 300.0,
    },
    "check_meme_tokens": {
        "task": "bot.memecoin.tasks.check_meme_tokens",
        "schedule": 120.0,
    },
    "check_deployer_wallets": {
        "task": "bot.memecoin.deployer.tasks.check_deployer_wallets",
        "schedule": 180.0,
    },
    # Check NFT collections every 5 minutes
    "check_nft_collections": {
        "task": "bot.nft.tasks.check_nft_collections",
        "schedule": 300.0,
    },
}