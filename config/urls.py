from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from library import views as library_views
from reader import views as reader_views

urlpatterns = [
    path("", reader_views.home, name="home"),
    path("", include("accounts.urls")),
    path("", include("backoffice.urls")),
    path("reader/", include("reader.urls")),
    path("admin/chapters/<int:pk>/publish", library_views.publish_chapter_view, name="admin-chapter-publish"),
    path("admin/watermark/extract", library_views.watermark_extract_view, name="admin-watermark-extract"),
    path("admin/", admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
