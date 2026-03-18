from django.contrib import admin
from .models import Category, Article


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['title', 'order', 'is_active', 'created_at', 'articles_count']
    list_filter = ['is_active', 'created_at']
    search_fields = ['title', 'description', 'tagline']
    list_editable = ['order', 'is_active']
    ordering = ['order', 'title']
    prepopulated_fields = {}
    
    fieldsets = (
        ('Category Information', {
            'fields': ('title', 'description', 'tagline')
        }),
        ('Display Settings', {
            'fields': ('order', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = ['created_at', 'updated_at']
    
    def articles_count(self, obj):
        return obj.articles.filter(is_published=True).count()
    articles_count.short_description = 'Published Articles'


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'order', 'is_published', 'created_at']
    list_filter = ['is_published', 'category', 'created_at']
    search_fields = ['title', 'content', 'excerpt']
    list_editable = ['order', 'is_published']
    ordering = ['category__order', 'order', 'title']
    prepopulated_fields = {'slug': ('title',)}
    
    fieldsets = (
        ('Article Information', {
            'fields': ('category', 'title', 'slug', 'excerpt')
        }),
        ('Content', {
            'fields': ('content',)
        }),
        ('Publishing Settings', {
            'fields': ('order', 'is_published')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = ['created_at', 'updated_at']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('category')
