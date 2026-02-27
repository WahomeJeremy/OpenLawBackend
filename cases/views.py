from rest_framework import generics, serializers
from rest_framework.response import Response
from django.db.models import Q
from .models import Case


class CaseSerializer(serializers.ModelSerializer):
    land_titles = serializers.SerializerMethodField()
    
    class Meta:
        model = Case
        fields = '__all__'
    
    def get_land_titles(self, obj):
        return [land.title_number for land in obj.lands.all()]


class CaseListView(generics.ListAPIView):
    """List all cases with optional search functionality"""
    queryset = Case.objects.all()
    serializer_class = CaseSerializer
    
    def get_queryset(self):
        queryset = Case.objects.all()
        search = self.request.query_params.get('search', None)
        
        if search:
            queryset = queryset.filter(
                Q(case_number__icontains=search) |
                Q(case_name__icontains=search) |
                Q(plaintiff__icontains=search) |
                Q(defendant__icontains=search) |
                Q(parties__icontains=search)
            )
        
        return queryset


class CaseDetailView(generics.RetrieveAPIView):
    """Get detailed information about a specific case"""
    queryset = Case.objects.all()
    serializer_class = CaseSerializer
