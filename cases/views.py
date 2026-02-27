from rest_framework import generics, serializers
from .models import Case


class CaseSerializer(serializers.ModelSerializer):
    land_titles = serializers.SerializerMethodField()
    
    class Meta:
        model = Case
        fields = '__all__'
    
    def get_land_titles(self, obj):
        return [land.title_number for land in obj.lands.all()]


class CaseListView(generics.ListAPIView):
    """List all cases"""
    queryset = Case.objects.all()
    serializer_class = CaseSerializer


class CaseDetailView(generics.RetrieveAPIView):
    """Get detailed information about a specific case"""
    queryset = Case.objects.all()
    serializer_class = CaseSerializer
