from django.contrib import admin

from .models import MemeAlert, MemeToken, TrackedDeployer


@admin.register(MemeToken)
class MemeTokenAdmin(admin.ModelAdmin):
    list_display = (
        "symbol",
        "chain",
        "status",
        "price_usd",
        "liquidity_usd",
        "market_cap_usd",
        "rugcheck_score",
        "is_pump_fun",
        "discovered_at",
    )
    list_filter = ("chain", "status", "is_pump_fun")
    search_fields = ("symbol", "name", "address", "pair_address")
    readonly_fields = ("discovered_at", "updated_at")


@admin.register(TrackedDeployer)
class TrackedDeployerAdmin(admin.ModelAdmin):
    list_display = ("address_short", "chain", "telegram_user", "label", "added_at")
    search_fields = ("address", "label", "telegram_user__username")

    @admin.display(description="Address")
    def address_short(self, obj):
        return f"{obj.address[:12]}…"


@admin.register(MemeAlert)
class MemeAlertAdmin(admin.ModelAdmin):
    list_display = ("alert_type", "token", "telegram_user", "sent_at")
    list_filter = ("alert_type",)
    readonly_fields = ("sent_at",)
