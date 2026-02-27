from rest_framework import generics, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import BlogPost


class BlogPostSerializer(serializers.ModelSerializer):
    class Meta:
        model = BlogPost
        fields = '__all__'


class BlogListView(generics.ListAPIView):
    """List all published blog posts"""
    queryset = BlogPost.objects.filter(is_published=True).order_by('-created_at')
    serializer_class = BlogPostSerializer


class BlogDetailView(generics.RetrieveAPIView):
    """Get detailed blog post by slug"""
    queryset = BlogPost.objects.filter(is_published=True)
    serializer_class = BlogPostSerializer
    lookup_field = 'slug'


class BlogInternalDashboard(APIView):
    """Internal dashboard for blog management (hidden URL)"""
    
    def get(self, request):
        """List all blog posts (including drafts)"""
        posts = BlogPost.objects.all().order_by('-created_at')
        serializer = BlogPostSerializer(posts, many=True)
        return Response(serializer.data)
    
    def post(self, request):
        """Create new blog post"""
        serializer = BlogPostSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def put(self, request, pk):
        """Update blog post"""
        try:
            post = BlogPost.objects.get(pk=pk)
            serializer = BlogPostSerializer(post, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except BlogPost.DoesNotExist:
            return Response({'error': 'Blog post not found'}, status=status.HTTP_404_NOT_FOUND)
    
    def delete(self, request, pk):
        """Delete blog post"""
        try:
            post = BlogPost.objects.get(pk=pk)
            post.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except BlogPost.DoesNotExist:
            return Response({'error': 'Blog post not found'}, status=status.HTTP_404_NOT_FOUND)
