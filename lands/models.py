from django.db import models


class Land(models.Model):
    title_number = models.CharField(max_length=255, db_index=True)
    lr_number = models.CharField(max_length=255, db_index=True, null=True, blank=True)
    plot_number = models.CharField(max_length=255, null=True, blank=True)
    certificate_number = models.CharField(max_length=255, null=True, blank=True)
    allotment_number = models.CharField(max_length=255, null=True, blank=True)
    county = models.CharField(max_length=100, null=True, blank=True)
    normalized_lr = models.CharField(max_length=255, db_index=True, null=True, blank=True, help_text="Normalized LR number without spaces or LR prefixes for accurate searching")
    title_system = models.CharField(max_length=20, null=True, blank=True, help_text="System type: LR or BLOCK")
    judgment_type = models.CharField(max_length=50, null=True, blank=True, help_text="Judgment type: Ruling or Judgment")
    plaintiff = models.CharField(max_length=255, null=True, blank=True)
    defendant = models.CharField(max_length=255, null=True, blank=True)
    court_station = models.CharField(max_length=255, null=True, blank=True)
    year_filed = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title_number

    @staticmethod
    def normalize_lr(value):
        """Normalize LR number format"""
        if not value:
            return ""
        return value.replace("LR", "").replace(".", "").strip().upper()


class SearchableReference(models.Model):
    """Searchable reference index for exact LR matching"""
    land = models.ForeignKey(Land, on_delete=models.CASCADE, related_name='searchable_references')
    reference_text = models.CharField(max_length=255, db_index=True)
    reference_type = models.CharField(max_length=20, choices=[
        ('LR', 'LR Number'),
        ('BLOCK', 'Block Number'),
        ('PLOT', 'Plot Number'),
        ('CERTIFICATE', 'Certificate Number'),
        ('ALLOTMENT', 'Allotment Number'),
    ])
    is_primary = models.BooleanField(default=False, help_text="Primary reference from original data")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['reference_text', 'reference_type']),
        ]

    def __str__(self):
        return f"{self.reference_type}: {self.reference_text}"
