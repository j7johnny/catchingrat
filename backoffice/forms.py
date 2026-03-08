from __future__ import annotations

from django import forms
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone

from accounts.models import User
from library.models import AntiOcrPreset, Chapter, ChapterStatus, Novel, ReaderChapterGrant, ReaderNovelGrant, ReaderSiteGrant


USERNAME_HELP = "帳號僅可使用英數字與 _.-，長度 1 到 16 字。"


class SetupAdminForm(forms.Form):
    username = forms.CharField(label="管理者帳號", max_length=16, help_text=USERNAME_HELP)
    password1 = forms.CharField(label="登入密碼", widget=forms.PasswordInput, strip=False)
    password2 = forms.CharField(label="再次輸入密碼", widget=forms.PasswordInput, strip=False)

    def clean_username(self):
        username = self.cleaned_data["username"].lower()
        field = User._meta.get_field("username")
        for validator in field.validators:
            validator(username)
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("此帳號已存在。")
        return username

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        username = cleaned_data.get("username")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "兩次輸入的密碼不一致。")
        if password1 and username:
            validate_password(password1, user=User(username=username, role=User.Role.ADMIN))
        return cleaned_data

    def save(self) -> User:
        return User.objects.create_superuser(
            username=self.cleaned_data["username"],
            password=self.cleaned_data["password1"],
        )


class ReaderCreateForm(forms.ModelForm):
    password1 = forms.CharField(label="初始密碼", widget=forms.PasswordInput, strip=False)
    password2 = forms.CharField(label="再次輸入密碼", widget=forms.PasswordInput, strip=False)

    class Meta:
        model = User
        fields = ["username", "is_active"]
        labels = {
            "username": "閱讀者帳號",
            "is_active": "帳號啟用",
        }
        help_texts = {"username": USERNAME_HELP}

    def clean_username(self):
        return self.cleaned_data["username"].lower()

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        username = cleaned_data.get("username")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "兩次輸入的密碼不一致。")
        if password1 and username:
            validate_password(password1, user=User(username=username, role=User.Role.READER))
        return cleaned_data

    def save(self, commit: bool = True) -> User:
        user = User(
            username=self.cleaned_data["username"],
            is_active=self.cleaned_data["is_active"],
            role=User.Role.READER,
        )
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class ReaderUpdateForm(forms.ModelForm):
    password1 = forms.CharField(
        label="重設密碼",
        widget=forms.PasswordInput,
        strip=False,
        required=False,
        help_text="若不需要重設密碼，可留空。",
    )
    password2 = forms.CharField(
        label="再次輸入新密碼",
        widget=forms.PasswordInput,
        strip=False,
        required=False,
    )

    class Meta:
        model = User
        fields = ["username", "is_active"]
        labels = {
            "username": "閱讀者帳號",
            "is_active": "帳號啟用",
        }
        help_texts = {"username": USERNAME_HELP}

    def clean_username(self):
        return self.cleaned_data["username"].lower()

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        if password1 or password2:
            if password1 != password2:
                self.add_error("password2", "兩次輸入的密碼不一致。")
            if password1:
                validate_password(password1, user=self.instance)
        return cleaned_data

    def save(self, commit: bool = True) -> User:
        user = super().save(commit=False)
        password = self.cleaned_data.get("password1")
        if password:
            user.set_password(password)
            user.password_changed_at = timezone.now()
        if commit:
            user.save()
        return user


class ReaderAccessForm(forms.Form):
    grant_full_site = forms.BooleanField(
        label="授權全站小說與章節",
        required=False,
        help_text="勾選後，這位閱讀者可閱讀所有目前與未來已發布的內容。",
    )
    novels = forms.ModelMultipleChoiceField(
        label="授權指定小說",
        queryset=Novel.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="授權整本小說後，該小說下所有已發布章節都可閱讀。",
    )
    chapters = forms.ModelMultipleChoiceField(
        label="授權指定章節",
        queryset=Chapter.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="只開放個別章節時使用。可與全站授權、小說授權並存。",
    )

    def __init__(self, *args, reader: User, **kwargs):
        self.reader = reader
        super().__init__(*args, **kwargs)
        self.fields["novels"].queryset = Novel.objects.filter(is_active=True).order_by("title")
        self.fields["chapters"].queryset = Chapter.objects.select_related("novel").order_by(
            "novel__title",
            "sort_order",
            "id",
        )
        if reader.pk:
            self.initial.setdefault("grant_full_site", ReaderSiteGrant.objects.filter(reader=reader).exists())
            self.initial.setdefault(
                "novels",
                list(ReaderNovelGrant.objects.filter(reader=reader).values_list("novel_id", flat=True)),
            )
            self.initial.setdefault(
                "chapters",
                list(ReaderChapterGrant.objects.filter(reader=reader).values_list("chapter_id", flat=True)),
            )

    def save(self, actor: User | None = None) -> None:
        if self.cleaned_data["grant_full_site"]:
            ReaderSiteGrant.objects.get_or_create(reader=self.reader, defaults={"granted_by": actor})
        else:
            ReaderSiteGrant.objects.filter(reader=self.reader).delete()

        selected_novels = set(self.cleaned_data["novels"].values_list("id", flat=True))
        existing_novels = {
            grant.novel_id: grant for grant in ReaderNovelGrant.objects.filter(reader=self.reader)
        }
        for novel_id, grant in existing_novels.items():
            if novel_id not in selected_novels:
                grant.delete()
        for novel in self.cleaned_data["novels"]:
            ReaderNovelGrant.objects.get_or_create(
                reader=self.reader,
                novel=novel,
                defaults={"granted_by": actor},
            )

        selected_chapters = set(self.cleaned_data["chapters"].values_list("id", flat=True))
        existing_chapters = {
            grant.chapter_id: grant for grant in ReaderChapterGrant.objects.filter(reader=self.reader)
        }
        for chapter_id, grant in existing_chapters.items():
            if chapter_id not in selected_chapters:
                grant.delete()
        for chapter in self.cleaned_data["chapters"]:
            ReaderChapterGrant.objects.get_or_create(
                reader=self.reader,
                chapter=chapter,
                defaults={"granted_by": actor},
            )


class NovelBackofficeForm(forms.ModelForm):
    class Meta:
        model = Novel
        fields = ["title", "slug", "description", "is_active"]
        labels = {
            "title": "小說名稱",
            "slug": "小說代稱",
            "description": "簡介",
            "is_active": "小說啟用",
        }
        help_texts = {
            "slug": "供系統內部辨識與管理使用，建議使用簡短、穩定、不重複的代稱。",
            "description": "可填寫給管理者看的簡介、備註或作品說明。",
        }


class ChapterBackofficeForm(forms.ModelForm):
    class Meta:
        model = Chapter
        fields = ["novel", "title", "slug", "sort_order", "anti_ocr_preset", "content"]
        labels = {
            "novel": "所屬小說",
            "title": "章節標題",
            "slug": "章節代稱",
            "sort_order": "章節排序",
            "anti_ocr_preset": "Anti-OCR 參數集",
            "content": "章節全文",
        }
        help_texts = {
            "slug": "供系統內部管理、搜尋與唯一性判斷使用，目前不會出現在讀者前台網址。",
            "sort_order": "數字越小越前面。若同一本小說內有多章，請依閱讀順序填寫。",
            "anti_ocr_preset": "留空時會使用目前的預設參數集。",
            "content": "請直接貼上完整章節內容。發布時會自動轉成防 OCR 圖片。",
        }
        widgets = {
            "content": forms.Textarea(attrs={"rows": 18}),
        }

    def save(self, commit: bool = True) -> Chapter:
        chapter = super().save(commit=False)
        if chapter.pk is None:
            chapter.status = ChapterStatus.DRAFT
        if commit:
            chapter.save()
        return chapter


class AntiOcrPresetSimpleForm(forms.ModelForm):
    class Meta:
        model = AntiOcrPreset
        fields = [
            "name",
            "is_default",
            "char_to_pinyin_ratio",
            "char_reverse_ratio",
            "desktop_width",
            "desktop_min_font_size",
            "desktop_max_font_size",
            "desktop_bg_density",
            "mobile_width",
            "mobile_min_font_size",
            "mobile_max_font_size",
            "mobile_bg_density",
        ]
        labels = {
            "name": "參數集名稱",
            "is_default": "設為全站預設",
            "char_to_pinyin_ratio": "轉拼音比例",
            "char_reverse_ratio": "倒字比例",
            "desktop_width": "桌機圖片寬度",
            "desktop_min_font_size": "桌機最小字級",
            "desktop_max_font_size": "桌機最大字級",
            "desktop_bg_density": "桌機背景干擾強度",
            "mobile_width": "手機圖片寬度",
            "mobile_min_font_size": "手機最小字級",
            "mobile_max_font_size": "手機最大字級",
            "mobile_bg_density": "手機背景干擾強度",
        }
        help_texts = {
            "name": "建議依用途命名，例如「預設可讀版」、「手機字體較大版」。",
            "is_default": "勾選後，未指定參數集的新章節會自動使用這組設定。",
            "char_to_pinyin_ratio": "將部份中文字替換成拼音的比例。第一版建議維持 0，以可讀性為主。",
            "char_reverse_ratio": "將部份字元做倒置的比例。第一版建議維持 0，避免影響閱讀。",
            "desktop_width": "桌機版圖片寬度，系統限制不可超過 600。",
            "desktop_min_font_size": "桌機版隨機字級下限。越大越好讀，但每張能容納的字數會變少。",
            "desktop_max_font_size": "桌機版隨機字級上限，需大於或等於最小字級。",
            "desktop_bg_density": "桌機版背景干擾強度。數值越高，防 OCR 越強，但也越容易干擾閱讀。",
            "mobile_width": "手機版圖片寬度，系統限制不可超過 600，建議維持 420。",
            "mobile_min_font_size": "手機版隨機字級下限，建議不要低於 20。",
            "mobile_max_font_size": "手機版隨機字級上限，需大於或等於最小字級。",
            "mobile_bg_density": "手機版背景干擾強度，建議先用低強度讓內容易讀。",
        }
        widgets = {
            "char_to_pinyin_ratio": forms.NumberInput(attrs={"step": "0.01", "min": "0", "max": "1"}),
            "char_reverse_ratio": forms.NumberInput(attrs={"step": "0.01", "min": "0", "max": "1"}),
            "desktop_bg_density": forms.NumberInput(attrs={"step": "0.01", "min": "0", "max": "1"}),
            "mobile_bg_density": forms.NumberInput(attrs={"step": "0.01", "min": "0", "max": "1"}),
        }

    def save(self, commit: bool = True) -> AntiOcrPreset:
        preset = super().save(commit=False)
        if commit:
            preset.save()
            if preset.is_default:
                AntiOcrPreset.objects.exclude(pk=preset.pk).filter(is_default=True).update(is_default=False)
        return preset


class WatermarkExtractToolForm(forms.Form):
    image = forms.ImageField(
        label="上傳待提取圖片",
        help_text="可上傳站內原圖、電腦截圖或多張閱讀切片拼成的長圖。",
    )
