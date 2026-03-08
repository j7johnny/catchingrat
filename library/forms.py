from django import forms

from library.models import AntiOcrPreset, Chapter, Novel


class WatermarkExtractForm(forms.Form):
    image = forms.ImageField(
        label="上傳圖片",
        help_text="可上傳站內原圖、瀏覽器另存圖片，或一般截圖做提取。",
    )


class NovelAdminForm(forms.ModelForm):
    class Meta:
        model = Novel
        fields = "__all__"
        help_texts = {
            "slug": "目前主要用於資料整理、唯一性與後台辨識；前台網址目前仍使用數字 ID。",
        }


class ChapterAdminForm(forms.ModelForm):
    class Meta:
        model = Chapter
        fields = "__all__"
        help_texts = {
            "slug": "目前主要用於資料整理、唯一性與後台辨識；前台閱讀網址目前仍使用章節 ID。",
            "sort_order": "同一本小說內的章節排序。數字越小越前面。",
            "anti_ocr_preset": "不選時會使用預設的 Anti-OCR 參數集。",
        }


class AntiOcrPresetAdminForm(forms.ModelForm):
    class Meta:
        model = AntiOcrPreset
        fields = "__all__"
        help_texts = {
            "name": "後台辨識用名稱，例如：預設、手機較清晰版、強防護版。",
            "is_default": "勾選後，未指定參數集的章節會使用這一組設定。",
            "char_to_pinyin_ratio": "把部分中文字替換成拼音的比例。你目前需求建議維持 0。",
            "char_reverse_ratio": "把部分文字反轉的比例。你目前需求建議維持 0，避免影響閱讀。",
            "desktop_width": "桌機版圖片寬度，最大只能到 600。",
            "desktop_min_font_size": "桌機版最小字級。數值越大越好讀，但每張可容納的字會變少。",
            "desktop_max_font_size": "桌機版最大字級。通常與最小字級接近即可，避免畫面跳動太大。",
            "desktop_bg_density": "桌機版背景干擾密度。越高越不利 OCR，但也越影響閱讀。",
            "mobile_width": "手機版圖片寬度，最大只能到 600。建議維持 420。",
            "mobile_min_font_size": "手機版最小字級。數值越大越好讀，但圖片張數會增加。",
            "mobile_max_font_size": "手機版最大字級。通常與最小字級接近即可。",
            "mobile_bg_density": "手機版背景干擾密度。建議從低值開始調整，以可讀性優先。",
        }
