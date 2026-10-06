from django.db import models


class PaymentTransaction(models.Model):
    """One row per STK Push attempt. Written at initiation, updated once (by
    the Daraja callback) when the customer approves, declines, or the
    request times out on their phone.

    ``checkout_request_id`` is Daraja's own identifier for the push -- the
    single value that ties our record to Safaricom's async callback, the
    same "create a reference now, resolve it later" shape as
    ``ndungu.CertificateLog`` / the public verify endpoint.
    """

    STATUS_CHOICES = [
        ("initiated", "Initiated"),
        ("pending", "Pending"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("timed_out", "Timed Out"),
    ]

    checkout_request_id = models.CharField(max_length=100, unique=True, db_index=True)
    merchant_request_id = models.CharField(max_length=100, blank=True)
    phone_number = models.CharField(max_length=15)
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    # What this payment is for -- the certificate reference goes in Daraja's
    # AccountReference field so it round-trips back to us unchanged.
    account_reference = models.CharField(max_length=100, db_index=True)
    transaction_desc = models.CharField(max_length=100, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="initiated")

    # Populated once the callback lands.
    mpesa_receipt_number = models.CharField(max_length=50, blank=True)
    result_code = models.IntegerField(null=True, blank=True)
    result_desc = models.CharField(max_length=255, blank=True)
    raw_callback = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.checkout_request_id} ({self.status})"
