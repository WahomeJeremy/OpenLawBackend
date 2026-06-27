import re

from django.db import models


def normalize_parcel_id(value: str) -> str:
    """Normalize a Parcel ID / LR number for exact matching.

    Standardizes case, strips L.R. NO. style prefixes, and tightens slashes
    and whitespace so format variants collapse to one canonical form, e.g.
    "L.R. No. 209 / 11642" -> "209/11642".
    """
    if not value:
        return ""
    s = value.upper()
    # Strip "L.R. NO." / "LR NO" / "L R" prefixes in their many OCR variants.
    s = re.sub(r"L\.?\s*R\.?\s*(?:NO\.?)?", " ", s)
    s = s.replace(".", " ")
    s = re.sub(r"\s*/\s*", "/", s)   # no spaces around slashes
    s = re.sub(r"\s+", " ", s).strip()
    return s


class Parcel(models.Model):
    """One unique flagged parcel from the Ndung'u Report (parcel_index.csv).

    The searchable unit. Aggregates one-or-more :class:`Finding` rows.
    """

    parcel_id_clean = models.CharField(max_length=255, unique=True, db_index=True)
    normalized_lr = models.CharField(max_length=255, db_index=True)
    parcel_display = models.TextField(blank=True)
    parcel_id_type = models.CharField(max_length=50, blank=True)   # lr / block / ...
    key_scope = models.CharField(max_length=20, blank=True)        # global / local
    n_findings = models.IntegerField(default=0)
    volumes = models.CharField(max_length=50, blank=True)          # e.g. "1;3"
    recommendations = models.TextField(blank=True)                 # rolled-up summary
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["parcel_id_clean"]
        indexes = [models.Index(fields=["normalized_lr"])]

    def save(self, *args, **kwargs):
        if not self.normalized_lr:
            self.normalized_lr = normalize_parcel_id(self.parcel_id_clean)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.parcel_display or self.parcel_id_clean


class Finding(models.Model):
    """One Ndung'u Report finding against a parcel (master_findings.csv),
    enriched with volume-specific transaction detail where available."""

    parcel = models.ForeignKey(
        Parcel, on_delete=models.CASCADE, related_name="findings"
    )
    record_id = models.CharField(max_length=255, db_index=True)
    parcel_id_raw = models.CharField(max_length=255, blank=True)
    parcel_id_type = models.CharField(max_length=50, blank=True)

    # Core finding (Tiers A & C)
    flag_category = models.CharField(max_length=255, blank=True)
    flag_reason = models.TextField(blank=True)
    current_holder = models.TextField(blank=True)      # owner at time of inquiry
    prior_party = models.TextField(blank=True)
    location = models.TextField(blank=True)
    area = models.CharField(max_length=100, blank=True)  # hectares (raw text)
    commission_recommendation = models.TextField(blank=True)

    # Source citation (Vol / Page)
    source_volume = models.CharField(max_length=20, blank=True)
    source_page = models.CharField(max_length=50, blank=True)
    flag_source_csv = models.CharField(max_length=255, blank=True)

    notes = models.TextField(blank=True)
    needs_manual_review = models.BooleanField(default=False)

    # --- Tier B enrichment (from flagged_parcels_vol*.csv, may be blank) ---
    reserved_use = models.TextField(blank=True)
    current_use = models.TextField(blank=True)
    allocating_authority = models.TextField(blank=True)
    transaction_date = models.CharField(max_length=100, blank=True)
    price_kshs = models.CharField(max_length=100, blank=True)
    allottee_id = models.CharField(max_length=255, blank=True)
    allottee_address = models.TextField(blank=True)
    legal_gazette_notice = models.TextField(blank=True)
    registration_date = models.CharField(max_length=100, blank=True)
    title_issue_date = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=255, blank=True)
    forest = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["source_volume", "source_page"]
        indexes = [models.Index(fields=["record_id"])]

    def __str__(self):
        return f"{self.record_id} ({self.flag_category})"


class CertificateLog(models.Model):
    """Immutable audit ledger. One row written on EVERY search execution.

    This is the single source of truth for the public verification portal:
    the verify endpoint resolves a ``certificate_reference`` back to this row.
    Rows are never updated or deleted.
    """

    STATUS_CHOICES = [
        ("encumbrance_found", "Encumbrance Found"),
        ("no_encumbrance", "No Encumbrance Recorded"),
        ("suggestions", "Suggestions Returned"),
    ]

    certificate_reference = models.CharField(max_length=40, unique=True, db_index=True)
    searched_parcel_id = models.CharField(max_length=255)  # exact input text
    normalized_query = models.CharField(max_length=255, blank=True)
    results_count = models.IntegerField(default=0)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES)
    matched_parcel = models.ForeignKey(
        Parcel, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="certificate_logs",
    )
    created_at = models.DateTimeField(auto_now_add=True)  # generation timestamp

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.certificate_reference} -> {self.searched_parcel_id}"
