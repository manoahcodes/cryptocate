"""
Management command: poll_wallets
Manually trigger a one-off wallet poll (useful for testing).

Usage:
    python manage.py poll_wallets
    python manage.py poll_wallets --address 0xd8da6BF26… --chain eth

Reference: https://docs.djangoproject.com/en/5.2/howto/custom-management-commands/
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Manually poll watched wallets for new transactions and send alerts."

    def add_arguments(self, parser):
        parser.add_argument(
            "--address",
            type=str,
            default=None,
            help="Only poll a specific wallet address.",
        )
        parser.add_argument(
            "--chain",
            type=str,
            default="eth",
            help="Chain to filter by when using --address (default: eth).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be checked without sending alerts.",
        )

    def handle(self, *args, **options):
        from bot.core.models import WatchedWallet
        from bot.multichain.router import check_wallet_for_alerts

        address = options.get("address")
        chain = options.get("chain", "eth")
        dry_run = options.get("dry_run", False)

        if address:
            wallets = WatchedWallet.objects.filter(
                address__iexact=address, chain=chain
            ).select_related("telegram_user", "telegram_user__user")
        else:
            wallets = WatchedWallet.objects.select_related(
                "telegram_user", "telegram_user__user"
            ).all()

        self.stdout.write(f"Polling {wallets.count()} wallet(s)…")

        checked = 0
        alerted = 0

        for wallet in wallets:
            if dry_run:
                self.stdout.write(
                    f"  [dry-run] Would check: {wallet.address[:12]}… "
                    f"({wallet.chain}) — threshold {wallet.effective_threshold()} ETH"
                )
                checked += 1
                continue

            try:
                alerts_sent = check_wallet_for_alerts(wallet)
                if alerts_sent:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  ✅ {wallet.address[:12]}… → {alerts_sent} alert(s) sent"
                        )
                    )
                else:
                    self.stdout.write(f"  — {wallet.address[:12]}… ({wallet.chain}) no new alerts")
                alerted += alerts_sent
                checked += 1
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f"  ❌ {wallet.address[:12]}… error: {e}"
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. Checked: {checked} | Alerts sent: {alerted}"
            )
        )
