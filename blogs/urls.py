from django.urls import path
from . import views

app_name = "blogs"

urlpatterns = [
    # Internal dashboard (must come before slug patterns)
    path("internal-dashboard/", views.BlogInternalDashboard.as_view(), name="internal_dashboard"),
    path("internal-dashboard/<int:pk>/", views.BlogInternalDashboard.as_view(), name="internal_dashboard_detail"),
    
    # Search endpoint
    path("search/", views.SearchView.as_view(), name="search"),
    
    # Category endpoints
    path("categories/", views.CategoryListView.as_view(), name="category_list"),
    path("categories/<int:pk>/", views.CategoryDetailView.as_view(), name="category_detail"),
    path("categories/<int:pk>/edit/", views.CategoryEditView.as_view(), name="category_edit"),
    
    # Article endpoints
    path("articles/", views.ArticleListView.as_view(), name="article_list"),
    path("articles/<slug:slug>/", views.ArticleDetailView.as_view(), name="article_detail"),
    path("articles/<int:pk>/edit/", views.ArticleEditView.as_view(), name="article_edit"),
    path("categories/<int:category_pk>/articles/<slug:slug>/", views.ArticleDetailView.as_view(), name="category_article_detail"),
    
    # Legacy endpoints (backward compatibility)
    path("", views.ArticleListView.as_view(), name="list"),
    path("<slug:slug>/", views.ArticleDetailView.as_view(), name="detail"),
]
