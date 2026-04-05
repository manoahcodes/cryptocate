"""
Initial migration for bot.memecoin models.
Reference: https://docs.djangoproject.com/en/5.2/topics/migrations/
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="MemeToken",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True,
                        serialize=False, verbose_name="ID",
                    ),
                ),
                ("address", models.CharField(db_index=True, max_length=100)),
                ("chain", models.CharField(default="eth", max_length=10)),
                ("symbol", models.CharField(blank=True, max_length=30)),
                ("name", models.CharField(blank=True, max_length=100)),
                ("pair_address", models.CharField(blank=True, max_length=100)),
                ("dex", models.CharField(blank=True, max_length=50)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("new", "New"),
                            ("watching", "Watching"),
                            ("graduated", "Graduated"),
                            ("dead", "Dead"),
                        ],
                        default="new",
                        max_length=20,
                    ),
                ),
                ("price_usd", models.FloatField(blank=True, null=True)),
                ("liquidity_usd", models.FloatField(blank=True, null=True)),
                ("market_cap_usd", models.FloatField(blank=True, null=True)),
                ("volume_1h", models.FloatField(blank=True, null=True)),
                ("buys_1h", models.IntegerField(blank=True, null=True)),
                ("sells_1h", models.IntegerField(blank=True, null=True)),
                ("rugcheck_score", models.FloatField(blank=True, null=True)),
                ("rugcheck_summary", models.TextField(blank=True)),
                ("rugcheck_checked_at", models.DateTimeField(blank=True, null=True)),
                ("is_pump_fun", models.BooleanField(default=False)),
                ("bonding_curve_pct", models.FloatField(blank=True, null=True)),
                ("graduated_at", models.DateTimeField(blank=True, null=True)),
                ("discovered_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Meme Token",
                "verbose_name_plural": "Meme Tokens",
            },
        ),
        migrations.CreateModel(
            name="TrackedDeployer",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True,
                        serialize=False, verbose_name="ID",
                    ),
                ),
                (
                    "telegram_user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tracked_deployers",
                        to="core.telegramuser",
                    ),
                ),
                ("address", models.CharField(db_index=True, max_length=100)),
                ("chain", models.CharField(default="eth", max_length=10)),
                ("label", models.CharField(blank=True, max_length=100)),
                ("last_seen_contract", models.CharField(blank=True, max_length=100)),
                ("added_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Tracked Deployer",
                "verbose_name_plural": "Tracked Deployers",
            },
        ),
        migrations.CreateModel(
            name="MemeAlert",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True,
                        serialize=False, verbose_name="ID",
                    ),
                ),
                (
                    "telegram_user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="meme_alerts",
                        to="core.telegramuser",
                    ),
                ),
                (
                    "token",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="alerts",
                        to="memecoin.memetoken",
                    ),
                ),
                (
                    "alert_type",
                    models.CharField(
                        choices=[
                            ("new_pair", "New Pair"),
                            ("whale_entry", "Whale Entry"),
                            ("momentum", "Momentum"),
                            ("pump_graduation", "Pump.fun Graduation"),
                            ("deployer_launch", "Deployer Launch"),
                            ("rug_risk", "Rug Risk"),
                        ],
                        max_length=30,
                    ),
                ),
                ("message_sent", models.TextField(blank=True)),
                ("sent_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Meme Alert",
                "verbose_name_plural": "Meme Alerts",
            },
        ),
        migrations.AddIndex(
            model_name="memetoken",
            index=models.Index(
                fields=["chain", "status"], name="meme_token_chain_status_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="memetoken",
            index=models.Index(
                fields=["discovered_at"], name="meme_token_discovered_idx"
            ),
        ),
        migrations.AlterUniqueTogether(
            name="memetoken",
            unique_together={("address", "chain")},
        ),
        migrations.AlterUniqueTogether(
            name="trackeddeployer",
            unique_together={("telegram_user", "address", "chain")},
        ),
        migrations.AddIndex(
            model_name="memealert",
            index=models.Index(
                fields=["telegram_user", "sent_at"], name="meme_alert_tg_date_idx"
            ),
        ),
    ]
