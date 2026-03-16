from django.db.models import Q
from rest_framework import generics, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Land, SearchableReference
import re


class LandSerializer(serializers.ModelSerializer):
    cases_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Land
        fields = '__all__'
    
    def get_cases_count(self, obj):
        return obj.cases.count()


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


def preprocess_search_query(raw_query):
    """
    Preprocess user search query by removing prefixes and normalizing.
    """
    if not raw_query:
        return ""
    
    # Only remove standalone prefixes, not "NO" when followed by other content
    query = re.sub(r'^(LR|L\.?R\.?|LAND\s+REFERENCE|PLOT|PARCEL|BLOCK|MUNICIPALITY\s*BLOCK)(?=\s|$)', '', raw_query, flags=re.IGNORECASE)
    
    # Remove dots and commas, but keep slashes
    query = re.sub(r'[.,\s]+', ' ', query)
    
    # Convert to uppercase and strip
    query = query.upper().strip()
    
    # Replace multiple spaces with single space
    query = re.sub(r'\s+', ' ', query)
    
    return query


def find_exact_matches(normalized_query):
    """
    Find exact matches using SearchableReference model.
    """
    # Exact match - no regex, just exact string matching
    matches = SearchableReference.objects.filter(
        reference_text__iexact=normalized_query
    ).select_related('land')
    
    return matches


def find_suggestions(normalized_query, limit=5):
    """
    Find close matches for suggestions.
    """
    # Find references that start with the query but are longer
    suggestions = SearchableReference.objects.filter(
        reference_text__istartswith=normalized_query
    ).exclude(
        reference_text__iexact=normalized_query
    ).select_related('land')[:limit]
    
    return suggestions


class LandSearchView(APIView):
    """Search for land by various identifiers"""
    
    def get(self, request):
        raw_query = request.GET.get('q', '').strip()
        
        if not raw_query:
            return Response({'error': 'Search query is required'}, status=400)
        
        # Validation: search term must be at least 3 characters
        if len(raw_query) < 3:
            return Response({
                'error': 'Please provide a more specific LR number (minimum 3 characters)'
            }, status=400)
        
        # Validation: search term must contain at least one digit to be a valid LR number
        if not re.search(r'\d', raw_query):
            return Response({
                'error': 'Invalid search format. LR numbers must contain at least one digit (e.g., LR 123/456, 1234, etc.)'
            }, status=400)
        
        # Preprocess query
        normalized_query = preprocess_search_query(raw_query)
        
        # Find exact matches
        exact_matches = find_exact_matches(normalized_query)
        
        if exact_matches.exists():
            # Return exact matches - remove duplicates by using set
            unique_lands = {}
            for match in exact_matches:
                unique_lands[match.land.id] = match.land
            
            lands = list(unique_lands.values())
            serializer = LandSerializer(lands, many=True)
            return Response({
                'query': raw_query,
                'results': serializer.data,
                'count': len(lands)
            })
        
        # No exact match found - try to find suggestions
        suggestions = SearchableReference.objects.filter(
            reference_text__istartswith=normalized_query
        ).exclude(
            reference_text__iexact=normalized_query
        ).select_related('land')[:5]
        
        if suggestions.exists():
            suggestion_texts = [s.reference_text for s in suggestions]
            return Response({
                'query': raw_query,
                'results': [],
                'count': 0,
                'message': f'No exact match found. Did you mean {", ".join(suggestion_texts[:3])}?'
            }, status=404)
        
        # No matches at all
        return Response({
            'query': raw_query,
            'results': [],
            'count': 0,
            'message': 'No exact records found'
        }, status=404)


class BulkLandSearchView(APIView):
    """Search for multiple land parcels in one request"""
    
    def post(self, request):
        serializer = BulkLandSearchSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        queries = serializer.validated_data['queries']
        results = []
        
        for raw_query in queries:
            raw_query = raw_query.strip()
            if not raw_query:
                results.append({
                    'query': raw_query,
                    'results': [],
                    'count': 0,
                    'message': 'Empty query'
                })
                continue
            
            # Validation: search term must be at least 3 characters
            if len(raw_query) < 3:
                results.append({
                    'query': raw_query,
                    'results': [],
                    'count': 0,
                    'message': 'Please provide a more specific LR number (minimum 3 characters)'
                })
                continue
            
            # Validation: search term must contain at least one digit to be a valid LR number
            if not re.search(r'\d', raw_query):
                results.append({
                    'query': raw_query,
                    'results': [],
                    'count': 0,
                    'message': 'Invalid search format. LR numbers must contain at least one digit (e.g., LR 123/456, 1234, etc.)'
                })
                continue
            
            # Use raw query for exact matching - no preprocessing
            search_query = raw_query.upper().strip()
            
            # Find exact matches
            exact_matches = SearchableReference.objects.filter(
                reference_text__iexact=search_query
            ).select_related('land').distinct('land')  # Remove duplicate land records
            
            if exact_matches.exists():
                # Return exact matches - remove duplicates by using set
                unique_lands = {}
                for match in exact_matches:
                    unique_lands[match.land.id] = match.land
                
                lands = list(unique_lands.values())
                land_serializer = LandSerializer(lands, many=True)
                results.append({
                    'query': raw_query,
                    'results': land_serializer.data,
                    'count': len(lands)
                })
            else:
                # No exact match found - try to find suggestions
                suggestions = SearchableReference.objects.filter(
                    reference_text__istartswith=search_query
                ).exclude(
                    reference_text__iexact=search_query
                ).select_related('land')[:5]
                
                if suggestions.exists():
                    suggestion_texts = [s.reference_text for s in suggestions]
                    results.append({
                        'query': raw_query,
                        'results': [],
                        'count': 0,
                        'message': f'No exact match found. Did you mean {", ".join(suggestion_texts[:3])}?'
                    })
                else:
                    # No matches at all
                    results.append({
                        'query': raw_query,
                        'results': [],
                        'count': 0,
                        'message': 'No exact records found'
                    })
        
        return Response({
            'results': results
        })


class LandDetailView(generics.RetrieveAPIView):
    """Get detailed information about a specific land parcel"""
    queryset = Land.objects.all()
    serializer_class = LandSerializer
