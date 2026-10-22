from django.urls import path

from . import views

app_name = "litigation"

urlpatterns = [
    path("review-request/", views.ReviewRequestView.as_view(), name="review_request"),
]
