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
    
    def get(self, request):
        query = request.GET.get('q', '').strip()
        
        if not query:
            return Response({'error': 'Search query is required'}, status=400)
        
        lands = Land.objects.filter(
            Q(title_number__icontains=query) |
            Q(lr_number__icontains=query) |
            Q(plot_number__icontains=query) |
            Q(certificate_number__icontains=query) |
            Q(allotment_number__icontains=query)
        ).distinct()
        
        serializer = LandSerializer(lands, many=True)
        return Response({
            'query': query,
            'results': serializer.data,
            'count': lands.count()
        })


class BulkLandSearchView(APIView):
    """Search for multiple land parcels in one request"""
    
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
                    'count': 0
                })
                continue
            
            lands = Land.objects.filter(
                Q(title_number__icontains=query) |
                Q(lr_number__icontains=query) |
                Q(plot_number__icontains=query) |
                Q(certificate_number__icontains=query) |
                Q(allotment_number__icontains=query)
            ).distinct()
            
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
