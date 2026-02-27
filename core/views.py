from django.shortcuts import render
from django.core.mail import send_mail
from django.conf import settings
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.decorators import api_view
from .models import LegalEmailApplication
from .serializers import LegalEmailApplicationSerializer


class LegalEmailApplicationListCreate(generics.ListCreateAPIView):
    queryset = LegalEmailApplication.objects.all()
    serializer_class = LegalEmailApplicationSerializer
    
    def perform_create(self, serializer):
        application = serializer.save()
        self.send_notification_email(application)
    
    def send_notification_email(self, application):
        subject = f"New @legal.ke Email Application: {application.full_name}"
        
        message = f"""
        New Legal.ke Email Application Received
        
        Applicant Details:
        - Full Name: {application.full_name}
        - Phone Number: {application.phone_number}
        - Account Type: {application.get_account_type_display()}
        - Occupation: {application.get_occupation_display()}
        - LSK Admission No: {application.lsk_admission_no or 'N/A'}
        - Current Email: {application.current_email}
        - Desired Email: {application.desired_email}@legal.ke
        - Application Date: {application.created_at.strftime('%Y-%m-%d %H:%M:%S')}
        - Status: {application.get_status_display()}
        
        Please review this application in the admin panel.
        """
        
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@legal.ke'),
                recipient_list=[getattr(settings, 'SUPPORT_EMAIL', 'support@legal.ke')],
                fail_silently=False,
            )
        except Exception as e:
            print(f"Failed to send email: {e}")


@api_view(['GET'])
def legal_email_applications_stats(request):
    total = LegalEmailApplication.objects.count()
    pending = LegalEmailApplication.objects.filter(status='pending').count()
    approved = LegalEmailApplication.objects.filter(status='approved').count()
    rejected = LegalEmailApplication.objects.filter(status='rejected').count()
    
    return Response({
        'total': total,
        'pending': pending,
        'approved': approved,
        'rejected': rejected
    })
