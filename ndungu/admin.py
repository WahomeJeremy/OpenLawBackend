from django.contrib import admin

from .models import Finding, Parcel


class FindingInline(admin.TabularInline):
    model = Finding
    extra = 0
    fields = ("flag_category", "current_holder", "commission_recommendation",
              "source_volume", "source_page")
    readonly_fields = fields
    can_delete = False


@admin.register(Parcel)
class ParcelAdmin(admin.ModelAdmin):
    list_display = ("parcel_id_clean", "parcel_id_type", "n_findings",
                    "volumes", "recommendations")
    search_fields = ("parcel_id_clean", "normalized_lr", "parcel_display")
    list_filter = ("parcel_id_type", "key_scope")
    inlines = [FindingInline]


@admin.register(Finding)
class FindingAdmin(admin.ModelAdmin):
    list_display = ("record_id", "parcel", "flag_category",
                    "source_volume", "source_page", "needs_manual_review")
    search_fields = ("record_id", "current_holder", "prior_party", "flag_reason")
    list_filter = ("source_volume", "flag_category", "needs_manual_review")
    raw_id_fields = ("parcel",)
