from django.db import models

from ndungu.models import normalize_parcel_id


class LrConversion(models.Model):
    """One canonical old-LR -> new-LR conversion under the 2017 Land
    Registration (Registration Units) Order.

    Reference data only -- this proves a parcel-number reissue, not an
    encumbrance. Deduplicated on (normalized_old_lr, normalized_new_lr): the
    same conversion is sometimes re-gazetted verbatim in a later special
    issue, and each occurrence is kept as a :class:`LrConversionCitation`
    rather than a duplicate row here.
    """

    old_lr_no = models.CharField(max_length=255)
    normalized_old_lr = models.CharField(max_length=255, db_index=True)
    new_lr_number = models.CharField(max_length=255)
    normalized_new_lr = models.CharField(max_length=255, db_index=True)
    new_parcel_no = models.CharField(max_length=50, blank=True)
    block = models.CharField(max_length=255, blank=True)
    scheme_name = models.CharField(max_length=255, blank=True)
    area_ha = models.CharField(max_length=50, blank=True)
    registration_unit = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["old_lr_no"]
        constraints = [
            models.UniqueConstraint(
                fields=["normalized_old_lr", "normalized_new_lr"],
                name="unique_old_new_lr_pair",
            )
        ]
        indexes = [
            models.Index(fields=["normalized_old_lr"]),
            models.Index(fields=["normalized_new_lr"]),
        ]

    def save(self, *args, **kwargs):
        if not self.normalized_old_lr:
            self.normalized_old_lr = normalize_parcel_id(self.old_lr_no)
        if not self.normalized_new_lr:
            self.normalized_new_lr = normalize_parcel_id(self.new_lr_number)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.old_lr_no} -> {self.new_lr_number}"


class LrConversionCitation(models.Model):
    """One gazette publication of a conversion (its audit trail). A
    conversion re-gazetted in a later special issue gets a second citation
    here rather than a duplicate LrConversion row."""

    conversion = models.ForeignKey(
        LrConversion, on_delete=models.CASCADE, related_name="citations"
    )
    gazette_notice_no = models.CharField(max_length=50, blank=True)
    gazette_vol_no = models.CharField(max_length=100, blank=True)
    gazette_date = models.CharField(max_length=100, blank=True)
    source_pdf = models.CharField(max_length=255, blank=True)
    source_page = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ["gazette_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["conversion", "source_pdf", "source_page"],
                name="unique_citation_per_page",
            )
        ]

    def __str__(self):
        return f"{self.conversion_id}: {self.source_pdf} p{self.source_page}"
