from django.urls import path
from . import views

app_name = "blogs"

urlpatterns = [
    path("", views.BlogListView.as_view(), name="list"),
    path("<slug:slug>/", views.BlogDetailView.as_view(), name="detail"),
    path("internal-dashboard/", views.BlogInternalDashboard.as_view(), name="internal_dashboard"),
    path("internal-dashboard/<int:pk>/", views.BlogInternalDashboard.as_view(), name="internal_dashboard_detail"),
]
