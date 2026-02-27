from django.db import models


class Case(models.Model):
    case_number = models.CharField(max_length=255, db_index=True)
    case_name = models.TextField()
    year = models.IntegerField(null=True, blank=True)
    court = models.CharField(max_length=255)
    status = models.CharField(max_length=100, null=True, blank=True)
    summary = models.TextField(null=True, blank=True)
    parties = models.TextField()
    plaintiff = models.TextField(null=True, blank=True)
    defendant = models.TextField(null=True, blank=True)
    lands = models.ManyToManyField("lands.Land", related_name="cases")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.case_number} - {self.case_name}"
