from django.urls import path
from . import views

app_name = "certificates"

urlpatterns = [
    path("generate/<int:land_id>/", views.CertificateGenerateView.as_view(), name="generate"),
    path("download/<uuid:pk>/", views.CertificateDownloadView.as_view(), name="download"),
    path("preview/<uuid:pk>/", views.CertificatePreviewView.as_view(), name="preview"),
]
