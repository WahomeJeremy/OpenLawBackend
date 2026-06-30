from django.db import models
from django.urls import reverse


class Category(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(help_text="Explain what stage of the journey this represents")
    tagline = models.TextField(help_text="A bold, memorable line that captures user emotion + intent")
    order = models.IntegerField(default=0, help_text="Display order for categories")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'title']
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('blogs:category_detail', kwargs={'pk': self.pk})


class Article(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="articles")
    title = models.CharField(max_length=255)
    content = models.TextField(help_text="Address a real user concern or question")
    slug = models.SlugField(unique=True, help_text="URL-friendly version of the title")
    excerpt = models.TextField(max_length=500, help_text="Brief summary of the article", blank=True)
    order = models.IntegerField(default=0, help_text="Display order within category")
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'title']
        unique_together = [['category', 'slug']]

    def __str__(self):
        return f"{self.category.title} - {self.title}"

    def get_absolute_url(self):
        return reverse('blogs:article_detail', kwargs={'category_pk': self.category.pk, 'slug': self.slug})
