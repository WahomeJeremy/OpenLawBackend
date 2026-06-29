from django.contrib import admin

from .models import BlogPost


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "order", "is_published", "created_at")
    list_filter = ("category", "is_published")
    list_editable = ("category", "order", "is_published")
    search_fields = ("title", "content")
    prepopulated_fields = {"slug": ("title",)}
