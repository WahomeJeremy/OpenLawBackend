from django.urls import path

from . import views

app_name = "payments"

urlpatterns = [
    path("initiate/", views.InitiatePaymentView.as_view(), name="initiate"),
    path("callback/", views.MpesaCallbackView.as_view(), name="callback"),
    path("<str:checkout_request_id>/status/", views.PaymentStatusView.as_view(), name="status"),
]
