from django.contrib import admin

from .models import PaymentTransaction


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "checkout_request_id", "account_reference", "phone_number",
        "amount", "status", "mpesa_receipt_number", "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("checkout_request_id", "account_reference", "phone_number", "mpesa_receipt_number")
    readonly_fields = [f.name for f in PaymentTransaction._meta.fields]
