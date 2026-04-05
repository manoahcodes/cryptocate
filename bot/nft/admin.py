from django.contrib import admin
from django.utils.html import format_html

from .models import NFTAlert, WatchedCollection


@admin.register(WatchedCollection)
class WatchedCollectionAdmin(admin.ModelAdmin):
    list_display = (
        "name_or_slug", "chain", "telegram_user",
        "floor_price_eth", "floor_price_usd",
        "floor_drop_pct", "floor_rise_pct",
        "last_checked_at",
    )
    list_filter  = ("chain",)
    search_fields = ("slug", "name", "telegram_user__username")
    readonly_fields = ("last_checked_at", "added_at",
                       "floor_price_eth", "floor_price_usd",
                       "volume_24h", "num_owners", "total_supply")

    @admin.display(description="Collection")
    def name_or_slug(self, obj):
        return obj.name or obj.slug


@admin.register(NFTAlert)
class NFTAlertAdmin(admin.ModelAdmin):
    list_display = (
        "alert_type", "collection", "telegram_user",
        "price_eth", "wallet_label", "sent_at",
    )
    list_filter  = ("alert_type",)
    search_fields = ("telegram_user__username", "wallet_address", "tx_hash")
    readonly_fields = ("sent_at",)