"""Import the LR-conversion dataset from data/conversions/conversion_master.csv.

One row per gazetted old-LR -> new-LR conversion, extracted from 15 Nairobi
"Special Issue" conversion gazettes (2017 Land Registration (Registration
Units) Order). Rows are grouped into one LrConversion per distinct
(old_lr_no, new_lr_number) pair; each row's gazette citation is kept as an
LrConversionCitation so a conversion re-gazetted in a later special issue
(a real, confirmed pattern in this data) shows every publication rather than
duplicating the conversion itself.

Usage:
    python manage.py import_conversions --flush
"""
import csv
import os

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from conversions.models import LrConversion, LrConversionCitation
from ndungu.models import normalize_parcel_id

DATA_FILE = os.path.join(settings.BASE_DIR, "data", "conversions", "conversion_master.csv")


class Command(BaseCommand):
    help = "Import the LR-conversion dataset (old LR -> new LR) from conversion_master.csv."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush", action="store_true",
            help="Delete all existing LrConversion/LrConversionCitation rows first.",
        )

    def handle(self, *args, **options):
        if not os.path.exists(DATA_FILE):
            self.stderr.write(f"Missing {DATA_FILE}")
            return

        if options["flush"]:
            n = LrConversion.objects.count()
            LrConversion.objects.all().delete()  # citations cascade
            self.stdout.write(f"Flushed {n} existing conversions.")

        # Group raw rows by the dedup key so republished conversions become
        # one LrConversion with multiple citations.
        groups = {}
        with open(DATA_FILE, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                key = (
                    normalize_parcel_id(row["old_lr_no"]),
                    normalize_parcel_id(row["new_lr_number"]),
                )
                groups.setdefault(key, []).append(row)

        created = updated = citations_created = 0
        with transaction.atomic():
            for (norm_old, norm_new), rows in groups.items():
                first = rows[0]
                conv, was_created = LrConversion.objects.update_or_create(
                    normalized_old_lr=norm_old,
                    normalized_new_lr=norm_new,
                    defaults=dict(
                        old_lr_no=first["old_lr_no"],
                        new_lr_number=first["new_lr_number"],
                        new_parcel_no=first.get("new_parcel_no", ""),
                        block=first.get("block", ""),
                        scheme_name=first.get("scheme_name", ""),
                        area_ha=first.get("area_ha", ""),
                        registration_unit=first.get("registration_unit", ""),
                    ),
                )
                created += was_created
                updated += not was_created

                for row in rows:
                    _, was_created = LrConversionCitation.objects.get_or_create(
                        conversion=conv,
                        source_pdf=row.get("source_pdf", ""),
                        source_page=row.get("source_page", ""),
                        defaults=dict(
                            gazette_notice_no=row.get("gazette_notice_no", ""),
                            gazette_vol_no=row.get("gazette_vol_no", ""),
                            gazette_date=row.get("gazette_date", ""),
                        ),
                    )
                    citations_created += was_created

        self.stdout.write(self.style.SUCCESS(
            f"Conversions: {created} created, {updated} updated, "
            f"{LrConversion.objects.count()} total | "
            f"Citations: {citations_created} created, "
            f"{LrConversionCitation.objects.count()} total"
        ))
