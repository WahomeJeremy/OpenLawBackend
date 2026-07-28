"""Sync ELC cases from the live 'INPUT FORM 1 (Responses)' Google Sheet.

The workbook has two response tabs -- both real, independent case logs, not
a duplicate/superseded pair -- so both are fetched and merged into the same
ElcCase table, keyed on case_citation.

The sheet is edited by volunteers throughout the day, so this command is
designed to be re-run on a schedule (Heroku Scheduler, daily) rather than run
once. Each run reflects the sheets' current state: cases are upserted by
citation, and each case's identifier list is replaced wholesale (so
corrections to a case's parcel numbers in the sheet are picked up, not just
appended to). A case removed from BOTH sheets is removed here too.

Usage:
    python manage.py sync_elc_litigation
"""
import csv
import io
import urllib.request
import urllib.error

from django.core.management.base import BaseCommand
from django.db import transaction

from litigation.models import ElcCase, ElcCaseIdentifier
from litigation.services import SHEET_EXPORT_URLS, split_identifiers

IDENTIFIER_COL_HINT = "title/plot/certificate/allotment/deed plan number"


def _find_column(fieldnames, hint):
    for name in fieldnames:
        if hint in name.strip().lower():
            return name
    return None


class Command(BaseCommand):
    help = "Sync ELC litigation cases from the public Google Sheet CSV exports (both tabs)."

    def _fetch_rows(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": "OpenLaw-ELC-Sync/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
        return list(csv.DictReader(io.StringIO(raw)))

    def handle(self, *args, **options):
        created = updated = skipped = 0
        seen_citations = set()
        total_identifiers = 0
        sheets_ok = 0

        for url in SHEET_EXPORT_URLS:
            try:
                rows = self._fetch_rows(url)
            except urllib.error.URLError as exc:
                self.stderr.write(f"Failed to fetch {url}: {exc}")
                continue
            if not rows:
                self.stderr.write(f"No rows returned from {url}")
                continue

            fieldnames = list(rows[0].keys())
            id_col = _find_column(fieldnames, IDENTIFIER_COL_HINT)
            if id_col is None:
                self.stderr.write(f"Could not find the identifier column among: {fieldnames}")
                continue
            parties_col = _find_column(fieldnames, "parties")
            location_col = _find_column(fieldnames, "location details")
            outcome_col = _find_column(fieldnames, "case outcome")
            sheets_ok += 1

            for row in rows:
                citation = (row.get("Case Citation") or "").strip()
                if not citation:
                    skipped += 1
                    continue
                seen_citations.add(citation)

                case, was_created = ElcCase.objects.update_or_create(
                    case_citation=citation,
                    defaults=dict(
                        url_link=(row.get("URL Link") or "").strip(),
                        court_station=(row.get("Court Station") or "").strip(),
                        judgment_date=(row.get("Judgement/Ruling Date") or "").strip(),
                        action=(row.get("Action") or "").strip(),
                        parties=(row.get(parties_col) or "").strip() if parties_col else "",
                        location_details=(row.get(location_col) or "").strip() if location_col else "",
                        outcome_status=(row.get(outcome_col) or "").strip() if outcome_col else "",
                        sheet_timestamp=(row.get("Timestamp") or "").strip(),
                    ),
                )
                created += was_created
                updated += not was_created

                pairs = split_identifiers(row.get(id_col))
                with transaction.atomic():
                    case.identifiers.all().delete()
                    for raw_id, normalized in pairs:
                        ElcCaseIdentifier.objects.get_or_create(
                            case=case, normalized_identifier=normalized,
                            defaults=dict(raw_identifier=raw_id),
                        )
                total_identifiers += len(pairs)

        if sheets_ok == 0:
            self.stderr.write("No sheets synced successfully -- aborting without deleting anything.")
            return

        # Cases removed from BOTH sheets (e.g. a bad row deleted by an editor)
        # are removed here too, so the dataset always mirrors the live sheets.
        removed, _ = ElcCase.objects.exclude(case_citation__in=seen_citations).delete()

        self.stdout.write(self.style.SUCCESS(
            f"ELC sync: {sheets_ok}/{len(SHEET_EXPORT_URLS)} sheets read | "
            f"{created} created, {updated} updated, {removed} removed, "
            f"{skipped} rows skipped (no citation), {total_identifiers} identifiers linked, "
            f"{ElcCase.objects.count()} total cases."
        ))
