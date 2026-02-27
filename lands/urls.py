from django.urls import path
from . import views

app_name = "lands"

urlpatterns = [
    path("", views.LandListView.as_view(), name="list"),
    path("search/", views.LandSearchView.as_view(), name="search"),
    path("bulk-search/", views.BulkLandSearchView.as_view(), name="bulk-search"),
    path("<uuid:pk>/", views.LandDetailView.as_view(), name="detail"),
]
