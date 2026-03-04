from django.db.models import Q
from rest_framework import generics, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination
from .models import Land


class LandPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class LandSerializer(serializers.ModelSerializer):
    cases_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Land
        fields = '__all__'
    
    def get_cases_count(self, obj):
        return obj.cases.count()


class LandListView(generics.ListAPIView):
    """List all land parcels"""
    queryset = Land.objects.all()
    serializer_class = LandSerializer
    pagination_class = LandPagination


class BulkLandSearchSerializer(serializers.Serializer):
    queries = serializers.ListField(
        child=serializers.CharField(max_length=255),
        min_length=1,
        max_length=50,
        help_text="List of land identifiers to search (title numbers, LR numbers, etc.)"
    )


class BulkLandSearchResultSerializer(serializers.Serializer):
    query = serializers.CharField()
    found = serializers.BooleanField()
    land_data = LandSerializer(required=False, allow_null=True)
    message = serializers.CharField(required=False, allow_blank=True)


class LandSearchView(APIView):
    """Search for land by various identifiers"""
    
    def is_valid_land_identifier(self, query):
        """Check if the query is a complete land identifier (not partial)"""
        # Remove common prefixes and clean the query
        cleaned_query = query.replace('LR', '').replace('TITLE', '').replace('NO.', '').replace('NUMBER', '').strip()
        
        # Check if it's too short to be a complete identifier
        if len(cleaned_query) < 3:
            return False
            
        # Check for patterns that suggest partial numbers (like single numbers, short fragments)
        # For example: "298" alone is likely partial, "7/298-299" is likely complete
        if len(cleaned_query) <= 4 and not any(char in cleaned_query for char in ['/', '-', ' ']):
            return False
        
        # Enhanced validation for slash-separated numbers
        if '/' in cleaned_query:
            parts = cleaned_query.split('/')
            # Must have at least 2 parts
            if len(parts) < 2:
                return False
            # Check if any part is too short (likely incomplete)
            for i, part in enumerate(parts):
                part = part.strip()
                # Allow single digits for first part (like "7" in "7/298-299")
                if i == 0 and len(part) == 1 and part.isdigit():
                    continue
                # For other parts, require at least 2 characters or meaningful content
                if len(part) < 2:
                    return False
                # If it's just numbers and very short (except first part), likely incomplete
                if part.isdigit() and len(part) <= 2 and i > 0:
                    return False
        
        # Enhanced validation for hyphen-separated numbers
        if '-' in cleaned_query:
            parts = cleaned_query.split('-')
            # Must have at least 2 parts
            if len(parts) < 2:
                return False
            # Check if any part is too short
            for part in parts:
                part = part.strip()
                # Allow 3-digit numbers (like "299" in "7/298-299")
                if len(part) == 3 and part.isdigit():
                    continue
                # For other parts, require at least 2 characters
                if len(part) < 2:
                    return False
                # If it's just numbers and very short, likely incomplete
                if part.isdigit() and len(part) <= 2:
                    return False
            
        return True
    
    def get(self, request):
        query = request.GET.get('q', '').strip()
        
        if not query:
            return Response({'error': 'Search query is required'}, status=400)
        
        # Validate that the query is a complete land identifier
        if not self.is_valid_land_identifier(query):
            return Response({
                'message': 'No land records found. Please confirm the LR number or title deed number and try again.',
                'query': query,
                'results': [],
                'count': 0
            }, status=404)
        
        lands = Land.objects.filter(
            Q(title_number__icontains=query) |
            Q(lr_number__icontains=query) |
            Q(plot_number__icontains=query) |
            Q(certificate_number__icontains=query) |
            Q(allotment_number__icontains=query)
        ).distinct()
        
        if not lands.exists():
            return Response({
                'message': 'No land records found. Please confirm the LR number or title deed number and try again.',
                'query': query,
                'results': [],
                'count': 0
            }, status=404)
        
        serializer = LandSerializer(lands, many=True)
        return Response({
            'query': query,
            'results': serializer.data,
            'count': lands.count()
        })


class BulkLandSearchView(APIView):
    """Search for multiple land parcels in one request"""
    
    def is_valid_land_identifier(self, query):
        """Check if the query is a complete land identifier (not partial)"""
        # Remove common prefixes and clean the query
        cleaned_query = query.replace('LR', '').replace('TITLE', '').replace('NO.', '').replace('NUMBER', '').strip()
        
        # Check if it's too short to be a complete identifier
        if len(cleaned_query) < 3:
            return False
            
        # Check for patterns that suggest partial numbers (like single numbers, short fragments)
        # For example: "298" alone is likely partial, "7/298-299" is likely complete
        if len(cleaned_query) <= 4 and not any(char in cleaned_query for char in ['/', '-', ' ']):
            return False
        
        # Enhanced validation for slash-separated numbers
        if '/' in cleaned_query:
            parts = cleaned_query.split('/')
            # Must have at least 2 parts
            if len(parts) < 2:
                return False
            # Check if any part is too short (likely incomplete)
            for i, part in enumerate(parts):
                part = part.strip()
                # Allow single digits for first part (like "7" in "7/298-299")
                if i == 0 and len(part) == 1 and part.isdigit():
                    continue
                # For other parts, require at least 2 characters or meaningful content
                if len(part) < 2:
                    return False
                # If it's just numbers and very short (except first part), likely incomplete
                if part.isdigit() and len(part) <= 2 and i > 0:
                    return False
        
        # Enhanced validation for hyphen-separated numbers
        if '-' in cleaned_query:
            parts = cleaned_query.split('-')
            # Must have at least 2 parts
            if len(parts) < 2:
                return False
            # Check if any part is too short
            for part in parts:
                part = part.strip()
                # Allow 3-digit numbers (like "299" in "7/298-299")
                if len(part) == 3 and part.isdigit():
                    continue
                # For other parts, require at least 2 characters
                if len(part) < 2:
                    return False
                # If it's just numbers and very short, likely incomplete
                if part.isdigit() and len(part) <= 2:
                    return False
            
        return True
    
    def post(self, request):
        serializer = BulkLandSearchSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        queries = serializer.validated_data['queries']
        results = []
        
        for query in queries:
            query = query.strip()
            if not query:
                results.append({
                    'query': query,
                    'results': [],
                    'count': 0,
                    'message': 'Empty query provided'
                })
                continue
            
            # Validate that the query is a complete land identifier
            if not self.is_valid_land_identifier(query):
                results.append({
                    'query': query,
                    'results': [],
                    'count': 0,
                    'message': 'No land records found. Please confirm the LR number or title deed number and try again.'
                })
                continue
            
            lands = Land.objects.filter(
                Q(title_number__icontains=query) |
                Q(lr_number__icontains=query) |
                Q(plot_number__icontains=query) |
                Q(certificate_number__icontains=query) |
                Q(allotment_number__icontains=query)
            ).distinct()
            
            if not lands.exists():
                results.append({
                    'query': query,
                    'results': [],
                    'count': 0,
                    'message': 'No land records found. Please confirm the LR number or title deed number and try again.'
                })
            else:
                land_serializer = LandSerializer(lands, many=True)
                results.append({
                    'query': query,
                    'results': land_serializer.data,
                    'count': lands.count()
                })
        
        return Response({
            'results': results
        })


class LandDetailView(generics.RetrieveAPIView):
    """Get detailed information about a specific land parcel"""
    queryset = Land.objects.all()
    serializer_class = LandSerializer
