"""Import the canonical Ndung'u Report dataset from data/ndungu/.

Loads parcel_index.csv -> Parcel and master_findings.csv -> Finding, enriching
each finding with volume-specific transaction detail (price, dates, allottee,
reserved/current use) joined by record_id from the flagged_parcels_vol*.csv files.

Usage:
    python manage.py import_ndungu --flush
"""
import csv
import os

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from ndungu.models import Finding, Parcel, normalize_parcel_id

DATA_DIR = os.path.join(settings.BASE_DIR, "data", "ndungu")

# Finding sources (same schema). master_findings is parcel-keyed; aux_findings
# is all narrative (no clean parcel id) — both load through _load_findings.
FINDING_FILES = ["master_findings.csv", "aux_findings.csv"]

# Volume-specific files that carry extra columns beyond master_findings.
ENRICH_FILES = [
    "flagged_parcels_vol1.csv",
    "flagged_parcels_vol2.csv",
    "flagged_parcels_vol3.csv",
    "flagged_parcels_vol3_forest.csv",
    "flagged_parcels_vol3_religious.csv",
]
ENRICH_COLS = [
    "reserved_use", "current_use", "allocating_authority", "transaction_date",
    "price_kshs", "allottee_id", "allottee_address", "legal_gazette_notice",
    "registration_date", "title_issue_date", "status", "forest",
]

# Non-parcel "descriptive entity" tables (schools, corporations, etc.). These
# have no LR/parcel number — they are searched by name/location. Each row
# becomes a typed Parcel (parcel_id_type = the entity type) + one Finding, so
# the existing search + certificate pipeline covers them too.
ENTITY_SOURCES = [
    {"file": "flagged_schools_vol1.csv", "type": "school", "volume": "1",
     "display": ["current_holder", "school_name"], "holder": "current_holder",
     "location": ["province"], "area": "area", "category": "flag_category",
     "recommendation": "commission_recommendation", "notes_cols": ["school_name"]},
    {"file": "flagged_entities_vol1.csv", "type": "entity", "volume": "1",
     "display": ["entity_name"], "holder": "entity_name",
     "category": "flag_category", "notes_cols": []},
    {"file": "flagged_corporations_vol1.csv", "type": "corporation", "volume": "1",
     "display": ["name"], "holder": "name", "category": "flag_category",
     "price": "sale_price", "date": "date_of_sale",
     "notes_cols": ["ownership_percent", "value_of_land", "size", "method",
                    "directors_at_time_of_sale", "land_price", "public_share_after"]},
    {"file": "flagged_complaints_vol2.csv", "type": "complaint", "volume": "2",
     "display": ["number_class_location"], "location": ["province"],
     "reason": "case_summary", "reserved": "planned_user",
     "notes_cols": ["s_no", "date_source_address"]},
    {"file": "flagged_road_reserves_vol1.csv", "type": "road_reserve", "volume": "1",
     "display": ["subject"], "reason_join": ["col2", "col3", "col4"],
     "notes_cols": []},
    {"file": "flagged_forest_excisions_vol2.csv", "type": "forest_excision",
     "volume": "2", "display": ["name_of_excision", "forest"], "holder": "beneficiary",
     "location": ["district", "province", "station"], "area": "excision_area_ha",
     "reserved": "forest", "recommendation": "recommendation",
     "notes_cols": ["legal_notice", "year", "purpose", "request", "status",
                    "legal_procedure", "remarks"]},
]


def _g(row, key):
    """Get a CSV cell as a stripped string; missing/None -> '' (blank, per spec)."""
    return (row.get(key) or "").strip()


def _truthy(value):
    return str(value).strip().lower() in ("1", "true", "yes")


def _first(row, cols):
    """First non-empty value among the given columns."""
    for c in cols:
        v = _g(row, c)
        if v:
            return v
    return ""


def _entity_display(row, cfg):
    name = _first(row, cfg.get("display", []))
    if name:
        return name
    return (f"{cfg['type'].replace('_', ' ').title()} "
            f"(Vol {cfg['volume']} p.{_g(row, 'source_page')})")


def _entity_finding(parcel, row, cfg):
    """Map an entity-table row onto a Finding using the source's config."""
    if cfg.get("reason"):
        reason = _g(row, cfg["reason"])
    elif cfg.get("reason_join"):
        reason = "; ".join(v for v in
                           (_g(row, c) for c in cfg["reason_join"]) if v)
    else:
        reason = (f"Flagged in the Ndung'u Report "
                  f"({cfg['type'].replace('_', ' ')}).")

    category = _g(row, cfg["category"]) if cfg.get("category") else ""
    notes = "; ".join(
        f"{c.replace('_', ' ').title()}: {_g(row, c)}"
        for c in cfg.get("notes_cols", []) if _g(row, c)
    )
    return Finding(
        parcel=parcel,
        record_id=parcel.parcel_id_clean,
        parcel_id_type=cfg["type"],
        flag_category=category or cfg["type"],
        flag_reason=reason,
        current_holder=_g(row, cfg["holder"]) if cfg.get("holder") else "",
        location=", ".join(v for v in
                           (_g(row, c) for c in cfg.get("location", [])) if v),
        area=_g(row, cfg["area"]) if cfg.get("area") else "",
        commission_recommendation=(
            _g(row, cfg["recommendation"]) if cfg.get("recommendation") else ""),
        reserved_use=_g(row, cfg["reserved"]) if cfg.get("reserved") else "",
        price_kshs=_g(row, cfg["price"]) if cfg.get("price") else "",
        transaction_date=_g(row, cfg["date"]) if cfg.get("date") else "",
        source_volume=cfg["volume"],
        source_page=_g(row, "source_page"),
        flag_source_csv=_g(row, "flag_source_csv"),
        notes=notes,
    )


class Command(BaseCommand):
    help = "Import Ndung'u Report parcels + findings from data/ndungu/."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush", action="store_true",
            help="Delete existing Parcel/Finding rows before importing.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        for required in ("parcel_index.csv", "master_findings.csv"):
            if not os.path.exists(os.path.join(DATA_DIR, required)):
                self.stderr.write(f"Missing {required} in {DATA_DIR}")
                return

        if options["flush"]:
            f_deleted = Finding.objects.count()
            p_deleted = Parcel.objects.count()
            Finding.objects.all().delete()
            Parcel.objects.all().delete()
            self.stdout.write(f"Flushed {p_deleted} parcels / {f_deleted} findings.")

        parcels = self._load_parcels()
        enrich = self._load_enrichment()
        self._load_findings(parcels, enrich)
        self._load_entities()

    # ------------------------------------------------------------------ #
    def _load_parcels(self):
        path = os.path.join(DATA_DIR, "parcel_index.csv")
        objs = []
        with open(path, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                pid = _g(r, "parcel_id_clean")
                if not pid:
                    continue
                objs.append(Parcel(
                    parcel_id_clean=pid,
                    normalized_lr=normalize_parcel_id(pid),
                    parcel_display=_g(r, "parcel_display"),
                    parcel_id_type=_g(r, "parcel_id_type"),
                    key_scope=_g(r, "key_scope"),
                    n_findings=int(_g(r, "n_findings") or 0),
                    volumes=_g(r, "volumes"),
                    recommendations=_g(r, "recommendations"),
                ))
        Parcel.objects.bulk_create(objs, batch_size=1000)
        parcels = {p.parcel_id_clean: p for p in Parcel.objects.all()}
        self.stdout.write(self.style.SUCCESS(f"Parcels loaded: {len(parcels)}"))
        return parcels

    def _load_enrichment(self):
        enrich = {}
        for fn in ENRICH_FILES:
            path = os.path.join(DATA_DIR, fn)
            if not os.path.exists(path):
                continue
            with open(path, newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                cols = [c for c in ENRICH_COLS if c in (reader.fieldnames or [])]
                for r in reader:
                    rid = _g(r, "record_id")
                    if rid:
                        enrich[rid] = {c: _g(r, c) for c in cols}
        self.stdout.write(f"Enrichment rows indexed: {len(enrich)}")
        return enrich

    def _load_findings(self, parcels, enrich):
        narrative = {}  # record_id -> synthetic Parcel for no-clean-id findings
        buffer, created, narr_count, orphan = [], 0, 0, 0

        for fname in FINDING_FILES:
            path = os.path.join(DATA_DIR, fname)
            if not os.path.exists(path):
                self.stdout.write(f"  (skipping missing {fname})")
                continue
            before = created + len(buffer)
            with open(path, newline="", encoding="utf-8") as fh:
                for r in csv.DictReader(fh):
                    pid = _g(r, "parcel_id_clean")
                    if pid:
                        parcel = parcels.get(pid)
                        if parcel is None:
                            # Defensive: parcel in findings but absent from index.
                            parcel = Parcel.objects.create(
                                parcel_id_clean=pid,
                                normalized_lr=normalize_parcel_id(pid),
                                parcel_display=_g(r, "parcel_display"),
                                parcel_id_type=_g(r, "parcel_id_type"),
                                key_scope=_g(r, "key_scope"),
                            )
                            parcels[pid] = parcel
                            orphan += 1
                    else:
                        # Narrative finding: no clean LR/parcel number. Give it its
                        # own parcel keyed by record_id, searchable via the
                        # name/location fallback path (PRD secondary search).
                        rid = _g(r, "record_id")
                        parcel = narrative.get(rid)
                        if parcel is None:
                            parcel = Parcel.objects.create(
                                parcel_id_clean=f"narrative::{rid}",
                                normalized_lr=normalize_parcel_id(_g(r, "parcel_id_raw")),
                                parcel_display=_g(r, "parcel_display"),
                                parcel_id_type="narrative",
                                key_scope="narrative",
                            )
                            narrative[rid] = parcel
                            narr_count += 1

                    ex = enrich.get(_g(r, "record_id"), {})
                    buffer.append(Finding(
                        parcel=parcel,
                        record_id=_g(r, "record_id"),
                        parcel_id_raw=_g(r, "parcel_id_raw"),
                        parcel_id_type=_g(r, "parcel_id_type"),
                        flag_category=_g(r, "flag_category"),
                        flag_reason=_g(r, "flag_reason"),
                        current_holder=_g(r, "current_holder"),
                        prior_party=_g(r, "prior_party"),
                        location=_g(r, "location"),
                        area=_g(r, "area"),
                        commission_recommendation=_g(r, "commission_recommendation"),
                        source_volume=_g(r, "source_volume"),
                        source_page=_g(r, "source_page"),
                        flag_source_csv=_g(r, "flag_source_csv"),
                        notes=_g(r, "notes"),
                        needs_manual_review=_truthy(_g(r, "needs_manual_review")),
                        reserved_use=ex.get("reserved_use", ""),
                        current_use=ex.get("current_use", ""),
                        allocating_authority=ex.get("allocating_authority", ""),
                        transaction_date=ex.get("transaction_date", ""),
                        price_kshs=ex.get("price_kshs", ""),
                        allottee_id=ex.get("allottee_id", ""),
                        allottee_address=ex.get("allottee_address", ""),
                        legal_gazette_notice=ex.get("legal_gazette_notice", ""),
                        registration_date=ex.get("registration_date", ""),
                        title_issue_date=ex.get("title_issue_date", ""),
                        status=ex.get("status", ""),
                        forest=ex.get("forest", ""),
                    ))
                    if len(buffer) >= 2000:
                        Finding.objects.bulk_create(buffer, batch_size=1000)
                        created += len(buffer)
                        buffer = []
            # Flush remainder per file so the per-file tally is accurate.
            if buffer:
                Finding.objects.bulk_create(buffer, batch_size=1000)
                created += len(buffer)
                buffer = []
            self.stdout.write(f"  {fname}: +{created - before} findings")

        self.stdout.write(self.style.SUCCESS(
            f"Findings loaded: {created} | narrative parcels (no clean id): "
            f"{narr_count} | orphan parcels (missing from index): {orphan}"
        ))

    # ------------------------------------------------------------------ #
    def _load_entities(self):
        """Load the descriptive entity tables (schools, corporations, etc.)
        as typed, name-searchable Parcel + Finding rows."""
        total = 0
        by_type = {}
        for cfg in ENTITY_SOURCES:
            path = os.path.join(DATA_DIR, cfg["file"])
            if not os.path.exists(path):
                self.stdout.write(f"  (skipping missing {cfg['file']})")
                continue

            staged = []  # (parcel_id_clean, row)
            parcels = []
            with open(path, newline="", encoding="utf-8") as fh:
                for i, row in enumerate(csv.DictReader(fh)):
                    pid = f"{cfg['type']}::{i}"
                    parcels.append(Parcel(
                        parcel_id_clean=pid,
                        normalized_lr="",
                        parcel_display=_entity_display(row, cfg),
                        parcel_id_type=cfg["type"],
                        key_scope="entity",
                    ))
                    staged.append((pid, row))
            Parcel.objects.bulk_create(parcels, batch_size=1000)

            pmap = {p.parcel_id_clean: p for p in
                    Parcel.objects.filter(parcel_id_type=cfg["type"])}
            findings = [_entity_finding(pmap[pid], row, cfg) for pid, row in staged]
            Finding.objects.bulk_create(findings, batch_size=1000)

            by_type[cfg["type"]] = len(findings)
            total += len(findings)
            self.stdout.write(f"  {cfg['file']}: +{len(findings)} ({cfg['type']})")

        self.stdout.write(self.style.SUCCESS(
            f"Entities loaded: {total} {by_type}"
        ))
