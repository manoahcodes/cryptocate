"""
Django admin registration for core models.
Reference: https://docs.djangoproject.com/en/5.2/ref/contrib/admin/
"""

from django.contrib import admin
from django.utils.html import format_html

from .models import Alert, TelegramUser, WalletScore, WatchedWallet


@admin.register(TelegramUser)
class TelegramUserAdmin(admin.ModelAdmin):
    list_display = (
        "telegram_id",
        "username",
        "first_name",
        "plan",
        "verified_email_display",
        "registration_complete_display",
        "wallet_count",
        "created_at",
    )
    list_filter = ("plan",)
    search_fields = ("telegram_id", "username", "first_name", "user__email")
    readonly_fields = (
        "telegram_id",
        "created_at",
        "updated_at",
        "verified_email_display",
        "registration_complete_display",
    )
    raw_id_fields = ("user",)

    @admin.display(description="Verified Email")
    def verified_email_display(self, obj):
        email = obj.verified_email
        if email:
            return format_html('<span style="color: green;">✓ {}</span>', email)
        return format_html('<span style="color: grey;">—</span>')

    @admin.display(description="Registered", boolean=True)
    def registration_complete_display(self, obj):
        return obj.registration_complete

    @admin.display(description="Wallets")
    def wallet_count(self, obj):
        return obj.wallets.count()


@admin.register(WatchedWallet)
class WatchedWalletAdmin(admin.ModelAdmin):
    list_display = (
        "address_short",
        "chain",
        "telegram_user",
        "label",
        "custom_threshold_eth",
        "dormant_alerted",
        "last_checked_at",
        "added_at",
    )
    list_filter = ("chain", "dormant_alerted")
    search_fields = ("address", "label", "telegram_user__username")
    raw_id_fields = ("telegram_user",)

    @admin.display(description="Address")
    def address_short(self, obj):
        return f"{obj.address[:8]}…{obj.address[-6:]}"


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = (
        "alert_type",
        "telegram_user",
        "tx_hash_short",
        "amount_eth",
        "amount_usd",
        "direction",
        "exchange_label",
        "sent_at",
    )
    list_filter = ("alert_type", "direction")
    search_fields = ("tx_hash", "telegram_user__username", "token_symbol")
    readonly_fields = ("sent_at",)

    @admin.display(description="TX Hash")
    def tx_hash_short(self, obj):
        return obj.tx_hash[:16] + "…" if obj.tx_hash else "—"


@admin.register(WalletScore)
class WalletScoreAdmin(admin.ModelAdmin):
    list_display = (
        "wallet",
        "score",
        "win_rate",
        "avg_return_pct",
        "total_trades",
        "calculated_at",
    )
    list_filter = ()
    search_fields = ("wallet__address",)
    readonly_fields = ("calculated_at",)
