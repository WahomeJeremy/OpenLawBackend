from rest_framework import serializers
from .models import LegalEmailApplication


class LegalEmailApplicationSerializer(serializers.ModelSerializer):
    class Meta:
        model = LegalEmailApplication
        fields = [
            'id', 'full_name', 'phone_number', 'account_type', 
            'occupation', 'lsk_admission_no', 'current_email', 
            'desired_email', 'status', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'status', 'created_at', 'updated_at']
    
    def validate_desired_email(self, value):
        if '@' in value:
            raise serializers.ValidationError("Desired email should only contain the username part (before @legal.ke)")
        return value
