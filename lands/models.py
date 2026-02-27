from django.db import models


class Land(models.Model):
    title_number = models.CharField(max_length=255, db_index=True)
    lr_number = models.CharField(max_length=255, db_index=True, null=True, blank=True)
    plot_number = models.CharField(max_length=255, null=True, blank=True)
    certificate_number = models.CharField(max_length=255, null=True, blank=True)
    allotment_number = models.CharField(max_length=255, null=True, blank=True)
    county = models.CharField(max_length=100, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title_number

    @staticmethod
    def normalize_lr(value):
        """Normalize LR number format"""
        if not value:
            return ""
        return value.replace("LR", "").replace(".", "").strip().upper()
