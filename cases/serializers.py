from rest_framework import serializers
from .models import Case


class CaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Case
        fields = ('id', 'case_number', 'case_name', 'year', 'court', 'status', 'summary', 
                  'parties', 'plaintiff', 'defendant', 'created_at')
