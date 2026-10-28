from django.urls import path

from . import views

app_name = "ndungu"

urlpatterns = [
    path("search/", views.SearchView.as_view(), name="search"),
    path("certificate/", views.CertificatePDFView.as_view(), name="certificate"),
    path("request-pages/", views.PageRequestView.as_view(), name="request_pages"),
    path("verify/<str:reference>/", views.VerifyView.as_view(), name="verify"),
]
