from django.urls import path

from . import views

app_name = "backoffice"

urlpatterns = [
    path("setup/", views.setup_view, name="setup"),
    path("manage/", views.dashboard, name="dashboard"),
    path("manage/readers/", views.reader_list, name="reader-list"),
    path("manage/readers/new/", views.reader_create, name="reader-create"),
    path("manage/readers/<int:user_id>/", views.reader_update, name="reader-update"),
    path("manage/novels/", views.novel_list, name="novel-list"),
    path("manage/novels/new/", views.novel_create, name="novel-create"),
    path("manage/novels/<int:novel_id>/", views.novel_detail, name="novel-detail"),
    path("manage/chapters/new/", views.chapter_create, name="chapter-create"),
    path("manage/chapters/<int:chapter_id>/", views.chapter_detail, name="chapter-detail"),
    path("manage/chapters/<int:chapter_id>/publish/", views.chapter_publish, name="chapter-publish"),
    path("manage/settings/anti-ocr/", views.anti_ocr_preset_list, name="anti-ocr-list"),
    path("manage/settings/anti-ocr/new/", views.anti_ocr_preset_create, name="anti-ocr-create"),
    path("manage/settings/anti-ocr/<int:preset_id>/", views.anti_ocr_preset_update, name="anti-ocr-update"),
    path("manage/settings/anti-ocr/fonts/", views.font_library, name="font-library"),
    path("manage/settings/anti-ocr/fonts/<int:font_id>/toggle/", views.font_toggle, name="font-toggle"),
    path("manage/settings/anti-ocr/fonts/<int:font_id>/delete/", views.font_delete, name="font-delete"),
    path("manage/tools/anti7ocr-diagnostics/", views.anti7ocr_diagnostics, name="anti7ocr-diagnostics"),
    path("manage/tools/watermark-extract/", views.watermark_extract, name="watermark-extract"),
    path(
        "manage/tools/watermark-extract/<int:record_id>/",
        views.watermark_extract_detail,
        name="watermark-extract-detail",
    ),
]
