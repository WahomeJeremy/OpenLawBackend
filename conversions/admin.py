from django.contrib import admin

from .models import LrConversion, LrConversionCitation


class LrConversionCitationInline(admin.TabularInline):
    model = LrConversionCitation
    extra = 0


@admin.register(LrConversion)
class LrConversionAdmin(admin.ModelAdmin):
    list_display = ("old_lr_no", "new_lr_number", "block", "area_ha", "registration_unit")
    search_fields = ("old_lr_no", "normalized_old_lr", "new_lr_number", "normalized_new_lr", "block")
    inlines = [LrConversionCitationInline]


@admin.register(LrConversionCitation)
class LrConversionCitationAdmin(admin.ModelAdmin):
    list_display = ("conversion", "gazette_vol_no", "gazette_date", "source_pdf", "source_page")
    search_fields = ("source_pdf", "gazette_notice_no")
