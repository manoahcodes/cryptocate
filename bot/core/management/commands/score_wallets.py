"""
Management command: score_wallets
Manually trigger profitability score recalculation for all Pro wallets.

Usage:
    python manage.py score_wallets
    python manage.py score_wallets --address 0xd8da6BF26… --chain eth

Reference: https://docs.djangoproject.com/en/5.2/howto/custom-management-commands/
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Recalculate profitability scores for Pro user wallets."

    def add_arguments(self, parser):
        parser.add_argument(
            "--address",
            type=str,
            default=None,
            help="Only score a specific wallet address.",
        )
        parser.add_argument(
            "--chain",
            type=str,
            default="eth",
            help="Chain to filter by when using --address (default: eth).",
        )
        parser.add_argument(
            "--all-plans",
            action="store_true",
            help="Score wallets for all users, not just Pro.",
        )

    def handle(self, *args, **options):
        from bot.core.models import WatchedWallet
        from bot.scoring.calculator import calculate_wallet_score

        address = options.get("address")
        chain = options.get("chain", "eth")
        all_plans = options.get("all_plans", False)

        qs = WatchedWallet.objects.select_related(
            "telegram_user", "score"
        )

        if address:
            qs = qs.filter(address__iexact=address, chain=chain)
        elif not all_plans:
            qs = qs.filter(telegram_user__plan="pro")

        total = qs.count()
        self.stdout.write(f"Scoring {total} wallet(s)…\n")

        scored = 0
        failed = 0

        for wallet in qs:
            try:
                result = calculate_wallet_score(wallet)
                if result:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  ✅ {wallet.address[:12]}… ({wallet.chain}): "
                            f"{result.score:.1f}/10 "
                            f"(win_rate={result.win_rate:.0%}, "
                            f"trades={result.total_trades})"
                        )
                    )
                    scored += 1
                else:
                    self.stdout.write(
                        f"  — {wallet.address[:12]}… ({wallet.chain}): skipped (insufficient data)"
                    )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f"  ❌ {wallet.address[:12]}… error: {e}"
                    )
                )
                failed += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. Scored: {scored} | Failed: {failed} | Total: {total}"
            )
        )
