"""
Initial migration for bot.directory models.
Reference: https://docs.djangoproject.com/en/5.2/topics/migrations/
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="DirectoryWallet",
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
                ("address", models.CharField(db_index=True, max_length=100)),
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
                ("label", models.CharField(max_length=120)),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("smart_money", "Smart Money"),
                            ("whale", "Whale"),
                            ("fund", "Fund / VC"),
                            ("dex_trader", "DEX Trader"),
                            ("nft", "NFT Whale"),
                            ("defi", "DeFi Power User"),
                            ("influencer", "Influencer"),
                            ("exchange", "Exchange"),
                            ("other", "Other"),
                        ],
                        default="whale",
                        max_length=20,
                    ),
                ),
                ("description", models.TextField(blank=True)),
                ("tags", models.CharField(
                    blank=True, max_length=200,
                    help_text="Comma-separated tags"
                )),
                ("is_verified", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                ("added_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Directory Wallet",
                "verbose_name_plural": "Directory Wallets",
                "ordering": ["-is_verified", "label"],
            },
        ),
        migrations.AddIndex(
            model_name="directorywallet",
            index=models.Index(
                fields=["chain", "category"],
                name="dir_wallet_chain_cat_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="directorywallet",
            index=models.Index(
                fields=["is_active"],
                name="dir_wallet_active_idx",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="directorywallet",
            unique_together={("address", "chain")},
        ),
    ]
