from django.urls import path
from . import views

app_name = "cases"

urlpatterns = [
    path("", views.CaseListView.as_view(), name="list"),
    path("<uuid:pk>/", views.CaseDetailView.as_view(), name="detail"),
]
