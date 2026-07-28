from django.contrib import admin

from .models import ElcCase, ElcCaseIdentifier


class ElcCaseIdentifierInline(admin.TabularInline):
    model = ElcCaseIdentifier
    extra = 0


@admin.register(ElcCase)
class ElcCaseAdmin(admin.ModelAdmin):
    list_display = ("case_citation", "action", "judgment_date", "court_station", "synced_at")
    search_fields = ("case_citation", "parties", "location_details")
    list_filter = ("action",)
    inlines = [ElcCaseIdentifierInline]


@admin.register(ElcCaseIdentifier)
class ElcCaseIdentifierAdmin(admin.ModelAdmin):
    list_display = ("normalized_identifier", "raw_identifier", "case")
    search_fields = ("normalized_identifier", "raw_identifier")
