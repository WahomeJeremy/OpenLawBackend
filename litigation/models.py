from django.db import models


class ElcCase(models.Model):
    """One ELC (Environment and Land Court) case, sourced from the live
    'INPUT FORM 1 (Responses)' Google Form -- a continuously updated sheet of
    court-clerked judgments/rulings. Re-synced daily (see sync_elc_litigation);
    rows here reflect the sheet's current state, not a point-in-time import.

    Reference data only -- an ELC case touching a parcel is not itself an
    encumbrance finding.
    """

    case_citation = models.CharField(max_length=500, unique=True, db_index=True)
    url_link = models.URLField(max_length=500, blank=True)
    court_station = models.CharField(max_length=255, blank=True)
    judgment_date = models.CharField(max_length=100, blank=True)  # raw text; formats vary in the sheet
    action = models.CharField(max_length=50, blank=True)  # Judgement / Ruling
    parties = models.TextField(blank=True)
    location_details = models.TextField(blank=True)
    outcome_status = models.TextField(blank=True)
    sheet_timestamp = models.CharField(max_length=50, blank=True)  # form-submission time, raw text
    synced_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-synced_at"]

    def __str__(self):
        return self.case_citation


class ElcCaseIdentifier(models.Model):
    """One Title/Plot/LR/Certificate/Allotment/Deed-Plan number cited in a
    case's identifier column (that column is semicolon-separated and often
    lists several parcels per case)."""

    case = models.ForeignKey(ElcCase, on_delete=models.CASCADE, related_name="identifiers")
    raw_identifier = models.CharField(max_length=255)
    normalized_identifier = models.CharField(max_length=255, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["case", "normalized_identifier"],
                name="unique_identifier_per_case",
            )
        ]

    def __str__(self):
        return f"{self.raw_identifier} ({self.case_id})"
