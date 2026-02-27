import os
from django.db import models
from django.http import HttpResponse
from django.template.loader import render_to_string
from rest_framework import generics, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView
# from weasyprint import HTML, CSS  # Commented out - requires system dependencies
from .models import Certificate
from lands.models import Land


class CertificateSerializer(serializers.ModelSerializer):
    land_title = serializers.CharField(source='land.title_number', read_only=True)
    ongoing_cases_count = serializers.SerializerMethodField()
    resolved_cases_count = serializers.SerializerMethodField()
    unknown_status_cases_count = serializers.SerializerMethodField()
    total_cases_count = serializers.SerializerMethodField()
    has_ongoing_litigation = serializers.SerializerMethodField()
    ongoing_cases = serializers.SerializerMethodField()
    resolved_cases = serializers.SerializerMethodField()
    unknown_status_cases = serializers.SerializerMethodField()
    
    class Meta:
        model = Certificate
        fields = '__all__'
    
    def get_ongoing_cases_count(self, obj):
        return obj.land.cases.filter(status__iexact='ruling').count()
    
    def get_resolved_cases_count(self, obj):
        return obj.land.cases.filter(status__iexact='judgment').count()
    
    def get_unknown_status_cases_count(self, obj):
        return obj.land.cases.filter(
            models.Q(status__isnull=True) | 
            models.Q(status='')
        ).count()
    
    def get_total_cases_count(self, obj):
        return obj.land.cases.count()
    
    def get_has_ongoing_litigation(self, obj):
        return obj.land.cases.filter(status__iexact='ruling').exists()
    
    def get_ongoing_cases(self, obj):
        view = CertificateGenerateView()
        return [view.enrich_case_data(case) for case in obj.land.cases.filter(status__iexact='ruling')]
    
    def get_resolved_cases(self, obj):
        view = CertificateGenerateView()
        return [view.enrich_case_data(case) for case in obj.land.cases.filter(status__iexact='judgment')]
    
    def get_unknown_status_cases(self, obj):
        view = CertificateGenerateView()
        return [view.enrich_case_data(case) for case in obj.land.cases.filter(
            models.Q(status__isnull=True) | 
            models.Q(status='')
        )]


class CertificateGenerateView(APIView):
    """Generate certificate for a land parcel"""
    
    def post(self, request, land_id):
        try:
            land = Land.objects.get(id=land_id)
            
            # Determine certificate type based on cases
            if land.cases.count() > 0:
                certificate_type = "CASE_LINKED"
            else:
                certificate_type = "CLEARANCE"
            
            # Create certificate
            certificate = Certificate.objects.create(
                land=land,
                certificate_type=certificate_type
            )
            
            # Generate PDF
            pdf_content = self.generate_certificate_pdf(certificate)
            
            # Save PDF file
            filename = f"certificate_{certificate.id}.pdf"
            file_path = os.path.join('certificates', filename)
            
            with open(f"media/{file_path}", 'wb') as f:
                f.write(pdf_content)
            
            certificate.pdf_file.name = file_path
            certificate.save()
            
            serializer = CertificateSerializer(certificate)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
            
        except Land.DoesNotExist:
            return Response({'error': 'Land not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def generate_certificate_pdf(self, certificate):
        """Generate PDF certificate using WeasyPrint (temporarily disabled)"""
        # TODO: Implement PDF generation once WeasyPrint is installed
        # For now, return a simple text-based certificate
        land = certificate.land
        all_cases = land.cases.all()
        
        # Categorize cases by status
        ongoing_cases = []
        resolved_cases = []
        unknown_status_cases = []
        
        for case in all_cases:
            status = case.status.lower() if case.status else ''
            case_data = self.enrich_case_data(case)
            
            if status == 'ruling':
                ongoing_cases.append(case_data)
            elif status == 'judgment':
                resolved_cases.append(case_data)
            else:
                unknown_status_cases.append(case_data)
        
        # Generate factual summary without recommendations
        context = {
            'certificate': certificate,
            'land': land,
            'all_cases': all_cases,
            'ongoing_cases': ongoing_cases,
            'resolved_cases': resolved_cases,
            'unknown_status_cases': unknown_status_cases,
            'has_ongoing_litigation': len(ongoing_cases) > 0,
            'has_resolved_cases': len(resolved_cases) > 0,
            'has_unknown_status': len(unknown_status_cases) > 0,
            'generated_date': certificate.generated_at.strftime('%d %B %Y'),
        }
        
        html_content = render_to_string('certificates/certificate_template.html', context)
        
        # For now, return HTML content that browsers can render as PDF
        # This will be replaced with proper PDF generation once WeasyPrint dependencies are resolved
        return html_content.encode('utf-8')

    def enrich_case_data(self, case):
        """Extract and enrich case data with plaintiff, defendant, and outcome information"""
        summary_text = case.summary or ''
        
        # Use plaintiff and defendant fields directly from database
        plaintiff = case.plaintiff or ''
        defendant = case.defendant or ''
        
        # Extract outcome information from summary for judgment cases
        outcome = ''
        if case.status and case.status.lower() == 'judgment':
            # Look for more specific outcome indicators in the summary
            outcome_indicators = [
                'judgment is entered',
                'ordered that',
                'granted',
                'dismissed',
                'awarded',
                'decided that',
                'finds that',
                'declares that',
                'it is ordered',
                'the court orders',
                'the court finds',
                'the court declares',
                'costs awarded',
                'in favor of',
                'against the',
                'appeal allowed',
                'appeal dismissed'
            ]
            
            summary_lower = summary_text.lower()
            for indicator in outcome_indicators:
                if indicator in summary_lower:
                    # Extract a larger portion of text around the indicator
                    start_pos = summary_lower.find(indicator)
                    if start_pos != -1:
                        # Start a bit earlier for context
                        context_start = max(0, start_pos - 50)
                        end_pos = start_pos + 300  # Get more text for better context
                        outcome = summary_text[context_start:end_pos].strip()
                        if len(outcome) > 10:
                            break
            
            # If no specific outcome found, use a generic message
            if not outcome:
                outcome = "Final judgment entered in this matter - consult full judgment for details"
        
        return {
            'id': case.id,
            'case_number': case.case_number,
            'case_name': case.case_name,
            'year': case.year,
            'status': case.status,
            'plaintiff': plaintiff,
            'defendant': defendant,
            'outcome': outcome,
            'court_station': case.court or 'Not specified'
        }


class CertificateDownloadView(generics.RetrieveAPIView):
    """Download certificate (HTML format for now)"""
    queryset = Certificate.objects.all()
    serializer_class = CertificateSerializer
    
    def retrieve(self, request, *args, **kwargs):
        certificate = self.get_object()
        
        # Generate certificate content on-demand
        generator = CertificateGenerateView()
        content = generator.generate_certificate_pdf(certificate)
        
        try:
            # Create better filename based on land title and certificate type
            land_title = certificate.land.title_number.replace('/', '_').replace(' ', '_')
            timestamp = certificate.generated_at.strftime('%Y%m%d_%H%M%S')
            filename = f"OpenLaw_Certificate_{land_title}_{timestamp}.html"
            
            # Return HTML content as downloadable file
            response = HttpResponse(content, content_type='text/html')
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
            
            return response
                
        except Exception as e:
            return Response({'error': f'Error generating certificate: {str(e)}'}, status=500)


class CertificatePreviewView(generics.RetrieveAPIView):
    """Preview certificate in browser"""
    queryset = Certificate.objects.all()
    serializer_class = CertificateSerializer
    
    def retrieve(self, request, *args, **kwargs):
        certificate = self.get_object()
        
        # Generate certificate content on-demand
        generator = CertificateGenerateView()
        content = generator.generate_certificate_pdf(certificate)
        
        try:
            # Return HTML content for inline display
            response = HttpResponse(content, content_type='text/html')
            response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
            
            return response
                
        except Exception as e:
            return Response({'error': f'Error generating certificate: {str(e)}'}, status=500)
