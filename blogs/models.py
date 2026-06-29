from django.db import models


class BlogPost(models.Model):
    CATEGORY_CHOICES = [
        ("due_diligence", "Due Diligence"),
        ("purchase", "Purchase"),
        ("transfer", "Transfer"),
        ("caution", "Caution"),
    ]

    title = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, max_length=255)
    category = models.CharField(
        max_length=30, choices=CATEGORY_CHOICES, default="due_diligence", db_index=True
    )
    order = models.IntegerField(default=0, help_text="Position within its category")
    content = models.TextField()
    excerpt = models.TextField(null=True, blank=True)
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["category", "order", "title"]

    def __str__(self):
        return self.title
