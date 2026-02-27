from django.db import models
import uuid


class Certificate(models.Model):
    CERTIFICATE_TYPES = [
        ("CASE_LINKED", "Case Linked Certificate"),
        ("CLEARANCE", "Clearance Certificate"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    land = models.ForeignKey("lands.Land", on_delete=models.CASCADE)
    certificate_type = models.CharField(max_length=50, choices=CERTIFICATE_TYPES)
    generated_at = models.DateTimeField(auto_now_add=True)
    pdf_file = models.FileField(upload_to="certificates/", null=True, blank=True)

    def __str__(self):
        return f"{self.certificate_type} - {self.land.title_number}"
