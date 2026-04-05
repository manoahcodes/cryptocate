from django.contrib import admin

from .models import DirectoryWallet


@admin.register(DirectoryWallet)
class DirectoryWalletAdmin(admin.ModelAdmin):
    list_display = (
        "label",
        "chain",
        "category",
        "address_short",
        "is_verified",
        "is_active",
        "added_at",
    )
    list_filter = ("chain", "category", "is_verified", "is_active")
    search_fields = ("label", "address", "description", "tags")
    list_editable = ("is_verified", "is_active")

    @admin.display(description="Address")
    def address_short(self, obj):
        return f"{obj.address[:10]}…"
