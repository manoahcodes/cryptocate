"""
Feature 3 — Whale Directory models.
Public database of known whale / smart-money wallets.
"""

from django.db import models


class DirectoryWallet(models.Model):
    """A curated whale wallet entry in the public directory."""

    CHAIN_CHOICES = [
        ("eth", "Ethereum"),
        ("arb", "Arbitrum"),
        ("base", "Base"),
        ("bsc", "BSC"),
        ("sol", "Solana"),
    ]

    CATEGORY_CHOICES = [
        ("smart_money", "Smart Money"),
        ("whale", "Whale"),
        ("fund", "Fund / VC"),
        ("dex_trader", "DEX Trader"),
        ("nft", "NFT Whale"),
        ("defi", "DeFi Power User"),
        ("influencer", "Influencer"),
        ("exchange", "Exchange"),
        ("other", "Other"),
    ]

    address = models.CharField(max_length=100, db_index=True)
    chain = models.CharField(max_length=10, choices=CHAIN_CHOICES, default="eth")
    label = models.CharField(max_length=120)
    category = models.CharField(
        max_length=20, choices=CATEGORY_CHOICES, default="whale"
    )
    description = models.TextField(blank=True)
    tags = models.CharField(max_length=200, blank=True, help_text="Comma-separated tags")
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    added_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("address", "chain")]
        indexes = [
            models.Index(fields=["chain", "category"]),
            models.Index(fields=["is_active"]),
        ]
        verbose_name = "Directory Wallet"
        verbose_name_plural = "Directory Wallets"
        ordering = ["-is_verified", "label"]
        app_label = "directory"

    def __str__(self):
        return f"{self.label} ({self.chain.upper()}: {self.address[:10]}…)"

    def tag_list(self) -> list[str]:
        if not self.tags:
            return []
        return [t.strip() for t in self.tags.split(",") if t.strip()]
