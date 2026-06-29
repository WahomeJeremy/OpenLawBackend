"""Import/upsert legal-resource articles from blogs/data/articles.json.

Each entry: {title, slug, category, order, excerpt, content(HTML)}.
Idempotent — keyed on slug, so re-running updates in place.

Usage:  python manage.py import_articles
"""
import json
import os

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.text import slugify

from blogs.models import BlogPost

DATA = os.path.join(settings.BASE_DIR, "blogs", "data", "articles.json")


class Command(BaseCommand):
    help = "Import/upsert blog articles from blogs/data/articles.json."

    def handle(self, *args, **options):
        if not os.path.exists(DATA):
            self.stderr.write(f"Missing {DATA}")
            return
        with open(DATA, encoding="utf-8") as fh:
            articles = json.load(fh)

        created = updated = 0
        for a in articles:
            slug = a.get("slug") or slugify(a["title"])
            _, was_created = BlogPost.objects.update_or_create(
                slug=slug,
                defaults={
                    "title": a["title"],
                    "category": a["category"],
                    "order": a.get("order", 0),
                    "content": a["content"],
                    "excerpt": a.get("excerpt", ""),
                    "is_published": a.get("is_published", True),
                },
            )
            created += was_created
            updated += not was_created

        self.stdout.write(self.style.SUCCESS(
            f"Articles: {created} created, {updated} updated | "
            f"total in DB: {BlogPost.objects.count()}"
        ))
        by_cat = {}
        for c, _ in BlogPost.CATEGORY_CHOICES:
            by_cat[c] = BlogPost.objects.filter(category=c).count()
        self.stdout.write(f"By category: {by_cat}")
