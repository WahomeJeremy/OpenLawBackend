from django import forms
from django.contrib import admin, messages

from .models import ElcCase, ElcCaseIdentifier, ManualReviewRequest
from .services import complete_review, notify_user_review_ready, original_search_summary


class ElcCaseIdentifierInline(admin.TabularInline):
    model = ElcCaseIdentifier
    extra = 0


@admin.register(ElcCase)
class ElcCaseAdmin(admin.ModelAdmin):
    list_display = ("case_citation", "action", "judgment_date", "court_station", "synced_at")
    search_fields = ("case_citation", "parties", "location_details")
    list_filter = ("action", "source")
    readonly_fields = ("source",)
    inlines = [ElcCaseIdentifierInline]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.source = "manual"  # hand-entered; the sheet sync leaves these alone
        super().save_model(request, obj, form, change)


@admin.register(ElcCaseIdentifier)
class ElcCaseIdentifierAdmin(admin.ModelAdmin):
    list_display = ("normalized_identifier", "raw_identifier", "case")
    search_fields = ("normalized_identifier", "raw_identifier")


class ManualReviewForm(forms.ModelForm):
    class Meta:
        model = ManualReviewRequest
        fields = "__all__"

    def clean(self):
        data = super().clean()
        outcome, cases = data.get("outcome"), data.get("cases")
        if outcome == ManualReviewRequest.OUTCOME_LITIGATION and not cases:
            self.add_error("cases", "Attach (or add with +) at least one case when litigation was found.")
        if outcome in (ManualReviewRequest.OUTCOME_CLEAR, ManualReviewRequest.OUTCOME_NOT_LOCATED) and cases:
            self.add_error("cases", "Remove the cases, or change the outcome to 'litigation found'.")
        return data


@admin.register(ManualReviewRequest)
class ManualReviewRequestAdmin(admin.ModelAdmin):
    """Staff queue. Setting an outcome and saving completes the review and
    emails the requester their link back to the app."""

    form = ManualReviewForm
    list_display = ("parcel_id", "status", "outcome", "contact_email", "contact_phone",
                    "certificate_reference", "created_at", "notified_at")
    list_filter = ("status", "outcome")
    search_fields = ("parcel_id", "contact_email", "contact_phone", "certificate_reference",
                     "review_reference", "notes")
    filter_horizontal = ("cases",)
    readonly_fields = ("original_search", "status", "review_reference", "reviewed_at",
                       "notified_at", "created_at")
    fieldsets = (
        ("Request", {"fields": ("parcel_id", "certificate_reference", "original_search", "contact_email",
                                "contact_phone", "notes", "created_at")}),
        ("Review outcome", {"fields": ("outcome", "cases"),
                            "description": "Choose the outcome and save to complete the review "
                                           "and notify the requester."}),
        ("Status", {"fields": ("status", "review_reference", "reviewed_at", "notified_at")}),
    )

    @admin.display(description="Original search")
    def original_search(self, obj):
        return original_search_summary(obj) or "No ledger entry for this reference."

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)  # saves the cases
        req = form.instance
        if not req.outcome:
            return
        first_completion = req.status != ManualReviewRequest.STATUS_DONE
        complete_review(req)
        if first_completion:
            if notify_user_review_ready(req):
                self.message_user(request, f"Review complete; {req.contact_email} has been emailed.")
            else:
                self.message_user(
                    request,
                    "Review complete, but no email was sent (no email address on the request). "
                    f"Contact them on {req.contact_phone or 'the details given'}.",
                    level=messages.WARNING,
                )
