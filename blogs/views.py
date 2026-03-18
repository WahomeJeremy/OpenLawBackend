from rest_framework import generics, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.db import models
from .models import Category, Article


class CategorySerializer(serializers.ModelSerializer):
    articles_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Category
        fields = ['id', 'title', 'description', 'tagline', 'order', 'is_active', 'articles_count']
    
    def get_articles_count(self, obj):
        return obj.articles.filter(is_published=True).count()


class ArticleSerializer(serializers.ModelSerializer):
    category_title = serializers.CharField(source='category.title', read_only=True)
    
    class Meta:
        model = Article
        fields = ['id', 'category', 'category_title', 'title', 'content', 'slug', 'excerpt', 'order', 'is_published', 'created_at', 'updated_at']


class ArticleDetailSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    
    class Meta:
        model = Article
        fields = ['id', 'category', 'title', 'content', 'slug', 'excerpt', 'created_at', 'updated_at']


class CategoryListView(generics.ListAPIView):
    """List all active categories representing user journey stages"""
    serializer_class = CategorySerializer
    
    def get_queryset(self):
        queryset = Category.objects.filter(is_active=True).order_by('order', 'title')
        search_query = self.request.query_params.get('search', None)
        
        if search_query:
            queryset = queryset.filter(
                models.Q(title__icontains=search_query) |
                models.Q(description__icontains=search_query) |
                models.Q(tagline__icontains=search_query)
            )
        
        return queryset


class CategoryDetailView(generics.RetrieveAPIView):
    """Get detailed category with its articles"""
    queryset = Category.objects.filter(is_active=True)
    serializer_class = CategorySerializer
    lookup_field = 'pk'


class ArticleListView(generics.ListAPIView):
    """List all published articles"""
    serializer_class = ArticleSerializer
    
    def get_queryset(self):
        queryset = Article.objects.filter(is_published=True).order_by('category__order', 'order', 'title')
        
        # Filter by category
        category_id = self.request.query_params.get('category')
        if category_id:
            queryset = queryset.filter(category_id=category_id)
        
        # Search functionality
        search_query = self.request.query_params.get('search', None)
        if search_query:
            queryset = queryset.filter(
                models.Q(title__icontains=search_query) |
                models.Q(content__icontains=search_query) |
                models.Q(excerpt__icontains=search_query) |
                models.Q(category__title__icontains=search_query)
            )
        
        return queryset


class ArticleDetailView(generics.RetrieveAPIView):
    """Get detailed article by slug"""
    queryset = Article.objects.filter(is_published=True)
    serializer_class = ArticleDetailSerializer
    lookup_field = 'slug'


class SearchView(generics.ListAPIView):
    """Advanced search endpoint for articles and categories"""
    serializer_class = ArticleSerializer
    
    def get_queryset(self):
        queryset = Article.objects.filter(is_published=True)
        
        # Search query
        search_query = self.request.query_params.get('search', None)
        if search_query:
            queryset = queryset.filter(
                models.Q(title__icontains=search_query) |
                models.Q(content__icontains=search_query) |
                models.Q(excerpt__icontains=search_query) |
                models.Q(category__title__icontains=search_query) |
                models.Q(category__description__icontains=search_query) |
                models.Q(category__tagline__icontains=search_query)
            )
        
        # Category filter
        category_id = self.request.query_params.get('category')
        if category_id:
            queryset = queryset.filter(category_id=category_id)
        
        # Ordering options
        order_by = self.request.query_params.get('order_by', 'category__order')
        valid_order_fields = ['category__order', 'order', 'title', 'created_at', '-created_at']
        if order_by in valid_order_fields:
            queryset = queryset.order_by(order_by)
        else:
            queryset = queryset.order_by('category__order', 'order', 'title')
        
        return queryset
    
    def get(self, request, *args, **kwargs):
        """Return search results with metadata"""
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response({
                'count': len(queryset),
                'results': serializer.data,
                'search_params': {
                    'search': request.query_params.get('search', ''),
                    'category': request.query_params.get('category', ''),
                    'order_by': request.query_params.get('order_by', 'category__order')
                }
            })
        
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'count': len(queryset),
            'results': serializer.data,
            'search_params': {
                'search': request.query_params.get('search', ''),
                'category': request.query_params.get('category', ''),
                'order_by': request.query_params.get('order_by', 'category__order')
            }
        })


@method_decorator(csrf_exempt, name='dispatch')
class CategoryEditView(generics.RetrieveUpdateDestroyAPIView):
    """Edit (GET/PUT/PATCH/DELETE) individual categories"""
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    lookup_field = 'pk'


@method_decorator(csrf_exempt, name='dispatch')
class ArticleEditView(generics.RetrieveUpdateDestroyAPIView):
    """Edit (GET/PUT/PATCH/DELETE) individual articles"""
    queryset = Article.objects.all()
    serializer_class = ArticleSerializer
    lookup_field = 'pk'


@method_decorator(csrf_exempt, name='dispatch')
class BlogInternalDashboard(APIView):
    """Internal dashboard for blog management (hidden URL)"""
    
    def get(self, request):
        """List all categories and articles (including drafts)"""
        categories = Category.objects.all().order_by('order', 'title')
        articles = Article.objects.all().order_by('category__order', 'order', 'title')
        
        category_serializer = CategorySerializer(categories, many=True)
        article_serializer = ArticleSerializer(articles, many=True)
        
        return Response({
            'categories': category_serializer.data,
            'articles': article_serializer.data
        })
    
    def post(self, request):
        """Create new category or article"""
        item_type = request.data.get('type')
        
        if item_type == 'category':
            serializer = CategorySerializer(data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
        elif item_type == 'article':
            serializer = ArticleSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def put(self, request, pk):
        """Update category or article"""
        item_type = request.data.get('type')
        
        try:
            if item_type == 'category':
                item = Category.objects.get(pk=pk)
                serializer = CategorySerializer(item, data=request.data, partial=True)
            elif item_type == 'article':
                item = Article.objects.get(pk=pk)
                serializer = ArticleSerializer(item, data=request.data, partial=True)
            else:
                return Response({'error': 'Invalid item type'}, status=status.HTTP_400_BAD_REQUEST)
            
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except (Category.DoesNotExist, Article.DoesNotExist):
            return Response({'error': 'Item not found'}, status=status.HTTP_404_NOT_FOUND)
    
    def delete(self, request, pk):
        """Delete category or article"""
        item_type = request.query_params.get('type')
        
        try:
            if item_type == 'category':
                item = Category.objects.get(pk=pk)
            elif item_type == 'article':
                item = Article.objects.get(pk=pk)
            else:
                return Response({'error': 'Invalid item type'}, status=status.HTTP_400_BAD_REQUEST)
            
            item.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except (Category.DoesNotExist, Article.DoesNotExist):
            return Response({'error': 'Item not found'}, status=status.HTTP_404_NOT_FOUND)
