"""
Management command: seed_directory
Loads the curated whale directory seed data into the database.

Usage:
    python manage.py seed_directory

Reference: https://docs.djangoproject.com/en/5.2/howto/custom-management-commands/
"""

from django.core.management.base import BaseCommand

from bot.directory.data import DIRECTORY_SEED
from bot.directory.models import DirectoryWallet


class Command(BaseCommand):
    help = "Seed the whale directory with curated known whale wallet addresses."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear all existing directory entries before seeding.",
        )

    def handle(self, *args, **options):
        if options["clear"]:
            count = DirectoryWallet.objects.count()
            DirectoryWallet.objects.all().delete()
            self.stdout.write(
                self.style.WARNING(f"Cleared {count} existing directory entries.")
            )

        created_count = 0
        updated_count = 0

        for entry in DIRECTORY_SEED:
            obj, created = DirectoryWallet.objects.update_or_create(
                address=entry["address"].lower(),
                chain=entry["chain"],
                defaults={
                    "label": entry["label"],
                    "category": entry.get("category", "whale"),
                    "description": entry.get("description", ""),
                    "tags": entry.get("tags", ""),
                    "is_verified": entry.get("is_verified", False),
                    "is_active": True,
                },
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Directory seeded: {created_count} created, {updated_count} updated. "
                f"Total: {DirectoryWallet.objects.count()} entries."
            )
        )
