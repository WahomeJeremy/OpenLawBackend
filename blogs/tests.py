from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from .models import Article, ArticleView, Category


class ArticleViewBeaconTests(TestCase):
    def setUp(self):
        cache.clear()
        cat = Category.objects.create(title="C", description="d", tagline="t")
        self.live = Article.objects.create(category=cat, title="A", content="x", slug="a")
        self.draft = Article.objects.create(
            category=cat, title="B", content="x", slug="b", is_published=False
        )

    def test_records_a_view_for_a_published_article(self):
        res = self.client.post(reverse("blogs:article_view", args=[self.live.pk]))
        self.assertEqual(res.status_code, 204)
        self.assertEqual(ArticleView.objects.filter(article=self.live).count(), 1)

    def test_each_open_is_its_own_event(self):
        url = reverse("blogs:article_view", args=[self.live.pk])
        self.client.post(url)
        self.client.post(url)
        self.assertEqual(ArticleView.objects.count(), 2)

    def test_unpublished_or_missing_article_is_404(self):
        for pk in (self.draft.pk, 99999):
            res = self.client.post(reverse("blogs:article_view", args=[pk]))
            self.assertEqual(res.status_code, 404)
        self.assertEqual(ArticleView.objects.count(), 0)

    def test_get_is_not_allowed(self):
        res = self.client.get(reverse("blogs:article_view", args=[self.live.pk]))
        self.assertEqual(res.status_code, 405)
