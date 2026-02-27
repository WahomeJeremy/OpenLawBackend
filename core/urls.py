from django.urls import path
from . import views

urlpatterns = [
    path('legal-email-applications/', views.LegalEmailApplicationListCreate.as_view(), name='legal-email-applications'),
    path('legal-email-applications/stats/', views.legal_email_applications_stats, name='legal-email-applications-stats'),
]
