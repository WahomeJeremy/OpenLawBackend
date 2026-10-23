import secrets

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
    # Which sheet tab the case was synced from (tab 1 = Nairobi, tab 2 = Kajiado);
    # the sheet's own Court Station column is almost always blank.
    county = models.CharField(max_length=50, blank=True)
    judgment_date = models.CharField(max_length=100, blank=True)  # raw text; formats vary in the sheet
    action = models.CharField(max_length=50, blank=True)  # Judgement / Ruling
    parties = models.TextField(blank=True)
    location_details = models.TextField(blank=True)
    outcome_status = models.TextField(blank=True)
    sheet_timestamp = models.CharField(max_length=50, blank=True)  # form-submission time, raw text
    # "manual" = entered by staff while completing a manual review; the sheet
    # sync must never delete these (they are not in the sheet).
    source = models.CharField(max_length=10, default="sheet", db_index=True)
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


def _new_access_token():
    return secrets.token_urlsafe(24)


class ManualReviewRequest(models.Model):
    """A user's request for staff to check a parcel by hand.

    ELC's indexed coverage has a known gap, so a "no ELC litigation recorded"
    certificate is not a guarantee. This is the user's way to ask us to look
    manually. Staff record the outcome here; the user is emailed a link
    (carrying `access_token`) back to the app to download the reviewed
    certificate. Reference data only -- it never changes a certificate's
    verdict for anyone else.
    """

    STATUS_PENDING = "pending"
    STATUS_DONE = "done"
    STATUS_CHOICES = [(STATUS_PENDING, "Pending"), (STATUS_DONE, "Done")]

    OUTCOME_CLEAR = "indexed_clear"
    OUTCOME_LITIGATION = "indexed_litigation"
    OUTCOME_NOT_LOCATED = "not_located"
    OUTCOME_CHOICES = [
        (OUTCOME_CLEAR, "Parcel indexed - no litigation found"),
        (OUTCOME_LITIGATION, "Parcel indexed - litigation found"),
        (OUTCOME_NOT_LOCATED, "Parcel could not be located"),
    ]

    parcel_id = models.CharField(max_length=255, db_index=True)
    certificate_reference = models.CharField(max_length=100, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=30, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    # Filled in by staff on completion.
    outcome = models.CharField(max_length=20, choices=OUTCOME_CHOICES, blank=True)
    cases = models.ManyToManyField(
        ElcCase, blank=True, related_name="manual_reviews",
        help_text="Cases found for this parcel. Use + to add a case by hand.",
    )
    review_reference = models.CharField(max_length=40, blank=True, editable=False)
    reviewed_at = models.DateTimeField(null=True, blank=True, editable=False)
    notified_at = models.DateTimeField(null=True, blank=True, editable=False)
    access_token = models.CharField(
        max_length=64, unique=True, default=_new_access_token, editable=False,
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.parcel_id} ({self.status})"
