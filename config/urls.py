from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse

def favicon_view(request):
    return HttpResponse(status=204)  # No Content

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("core.urls")),
    path("api/cases/", include("cases.urls")),
    path("api/lands/", include("lands.urls")),
    path("api/certificates/", include("certificates.urls")),
    path("api/blogs/", include("blogs.urls")),
    path("favicon.ico", favicon_view),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
