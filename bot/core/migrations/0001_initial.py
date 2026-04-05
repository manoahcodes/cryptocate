"""
Initial migration for bot.core models.
Reference: https://docs.djangoproject.com/en/5.2/topics/migrations/
"""

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TelegramUser",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "user",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="telegram_user",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                ("telegram_id", models.BigIntegerField(db_index=True, unique=True)),
                ("username", models.CharField(blank=True, max_length=120)),
                ("first_name", models.CharField(blank=True, max_length=120)),
                (
                    "plan",
                    models.CharField(
                        choices=[("free", "Free"), ("pro", "Pro")],
                        default="free",
                        max_length=10,
                    ),
                ),
                (
                    "paddle_customer_id",
                    models.CharField(blank=True, db_index=True, max_length=100),
                ),
                (
                    "paddle_subscription_id",
                    models.CharField(blank=True, db_index=True, max_length=100),
                ),
                ("subscription_ends_at", models.DateTimeField(blank=True, null=True)),
                ("digest_enabled", models.BooleanField(default=True)),
                ("digest_hour", models.IntegerField(default=8)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Telegram User",
                "verbose_name_plural": "Telegram Users",
            },
        ),
        migrations.CreateModel(
            name="WatchedWallet",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "telegram_user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="wallets",
                        to="core.telegramuser",
                    ),
                ),
                ("address", models.CharField(max_length=100)),
                (
                    "chain",
                    models.CharField(
                        choices=[
                            ("eth", "Ethereum"),
                            ("arb", "Arbitrum"),
                            ("base", "Base"),
                            ("bsc", "BSC"),
                            ("sol", "Solana"),
                        ],
                        default="eth",
                        max_length=10,
                    ),
                ),
                ("label", models.CharField(blank=True, max_length=100)),
                ("custom_threshold_eth", models.FloatField(blank=True, null=True)),
                ("last_seen_tx", models.CharField(blank=True, max_length=100)),
                ("last_checked_at", models.DateTimeField(blank=True, null=True)),
                ("dormant_alerted", models.BooleanField(default=False)),
                ("added_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Watched Wallet",
                "verbose_name_plural": "Watched Wallets",
            },
        ),
        migrations.CreateModel(
            name="Alert",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "telegram_user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="alerts",
                        to="core.telegramuser",
                    ),
                ),
                (
                    "wallet",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="alerts",
                        to="core.watchedwallet",
                    ),
                ),
                (
                    "alert_type",
                    models.CharField(
                        choices=[
                            ("transfer", "ETH Transfer"),
                            ("token", "Token Transfer"),
                            ("dormant", "Dormant Wallet"),
                            ("meme", "Memecoin"),
                            ("copy_trade", "Copy Trade Signal"),
                        ],
                        max_length=20,
                    ),
                ),
                ("tx_hash", models.CharField(blank=True, max_length=100)),
                ("amount_eth", models.FloatField(blank=True, null=True)),
                ("amount_usd", models.FloatField(blank=True, null=True)),
                ("token_symbol", models.CharField(blank=True, max_length=30)),
                ("direction", models.CharField(blank=True, max_length=10)),
                ("exchange_label", models.CharField(blank=True, max_length=50)),
                ("message_sent", models.TextField(blank=True)),
                ("sent_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Alert",
                "verbose_name_plural": "Alerts",
            },
        ),
        migrations.CreateModel(
            name="WalletScore",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "wallet",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="score",
                        to="core.watchedwallet",
                    ),
                ),
                ("score", models.FloatField(default=0.0)),
                ("win_rate", models.FloatField(default=0.0)),
                ("avg_return_pct", models.FloatField(default=0.0)),
                ("total_trades", models.IntegerField(default=0)),
                ("calculated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Wallet Score",
                "verbose_name_plural": "Wallet Scores",
            },
        ),
        migrations.AddIndex(
            model_name="telegramuser",
            index=models.Index(fields=["plan"], name="core_telgr_plan_idx"),
        ),
        migrations.AddIndex(
            model_name="watchedwallet",
            index=models.Index(
                fields=["telegram_user", "chain"], name="core_wallet_tg_chain_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="watchedwallet",
            index=models.Index(fields=["chain"], name="core_wallet_chain_idx"),
        ),
        migrations.AlterUniqueTogether(
            name="watchedwallet",
            unique_together={("telegram_user", "address", "chain")},
        ),
        migrations.AddIndex(
            model_name="alert",
            index=models.Index(
                fields=["telegram_user", "sent_at"], name="core_alert_tg_date_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="alert",
            index=models.Index(fields=["tx_hash"], name="core_alert_txhash_idx"),
        ),
    ]
