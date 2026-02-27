from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/lands/", include("lands.urls")),
    path("api/cases/", include("cases.urls")),
    path("api/certificates/", include("certificates.urls")),
    path("api/blogs/", include("blogs.urls")),
    path("api/core/", include("core.urls")),
]
