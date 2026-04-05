"""Initial migration for bot.nft models."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True
    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="WatchedCollection",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("telegram_user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="nft_collections", to="core.telegramuser")),
                ("slug",             models.CharField(max_length=120)),
                ("chain",            models.CharField(choices=[("eth","Ethereum"),("sol","Solana"),("base","Base"),("arb","Arbitrum")], default="eth", max_length=10)),
                ("name",             models.CharField(blank=True, max_length=200)),
                ("contract_address", models.CharField(blank=True, max_length=100)),
                ("floor_drop_pct",   models.FloatField(default=10.0)),
                ("floor_rise_pct",   models.FloatField(default=20.0)),
                ("volume_spike_x",   models.FloatField(default=3.0)),
                ("sweep_min_wallets",models.IntegerField(default=5)),
                ("floor_price_eth",  models.FloatField(blank=True, null=True)),
                ("floor_price_usd",  models.FloatField(blank=True, null=True)),
                ("volume_1h",        models.FloatField(blank=True, null=True)),
                ("volume_24h",       models.FloatField(blank=True, null=True)),
                ("num_owners",       models.IntegerField(blank=True, null=True)),
                ("total_supply",     models.IntegerField(blank=True, null=True)),
                ("volume_baseline",  models.FloatField(blank=True, null=True)),
                ("last_floor_alerted", models.FloatField(blank=True, null=True)),
                ("last_checked_at",  models.DateTimeField(blank=True, null=True)),
                ("added_at",         models.DateTimeField(auto_now_add=True)),
            ],
            options={"verbose_name": "Watched NFT Collection", "verbose_name_plural": "Watched NFT Collections", "app_label": "nft"},
        ),
        migrations.CreateModel(
            name="NFTAlert",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("telegram_user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="nft_alerts", to="core.telegramuser")),
                ("collection", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="alerts", to="nft.watchedcollection")),
                ("alert_type",     models.CharField(choices=[("floor_drop","Floor Price Drop"),("floor_rise","Floor Price Rise"),("volume_spike","Volume Spike"),("sweep","Collection Sweep"),("whale_buy","Whale Buy"),("whale_sell","Whale Sell"),("whale_mint","Whale Mint")], max_length=20)),
                ("tx_hash",        models.CharField(blank=True, max_length=100)),
                ("wallet_address", models.CharField(blank=True, max_length=100)),
                ("wallet_label",   models.CharField(blank=True, max_length=120)),
                ("token_id",       models.CharField(blank=True, max_length=50)),
                ("price_eth",      models.FloatField(blank=True, null=True)),
                ("price_usd",      models.FloatField(blank=True, null=True)),
                ("message_sent",   models.TextField(blank=True)),
                ("sent_at",        models.DateTimeField(auto_now_add=True)),
            ],
            options={"verbose_name": "NFT Alert", "verbose_name_plural": "NFT Alerts", "app_label": "nft"},
        ),
        migrations.AlterUniqueTogether(name="watchedcollection", unique_together={("telegram_user", "slug", "chain")}),
        migrations.AddIndex(model_name="watchedcollection", index=models.Index(fields=["telegram_user"], name="nft_col_user_idx")),
        migrations.AddIndex(model_name="watchedcollection", index=models.Index(fields=["chain"], name="nft_col_chain_idx")),
        migrations.AddIndex(model_name="nftalert", index=models.Index(fields=["telegram_user", "sent_at"], name="nft_alert_tg_date_idx")),
    ]