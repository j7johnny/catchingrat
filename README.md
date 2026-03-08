# CatchingRat

封閉式中文小說閱讀站測試專案，使用 `Django 6 + PostgreSQL + Redis + Celery + Nginx + Docker Compose`。

目前已提供：

- 管理員建立讀者帳號
- 讀者登入、登出、修改密碼
- 簡易防暴力破解
- 章節發布與 anti-OCR 圖片產生
- 每日個人化隱藏浮水印圖片
- 管理後台浮水印提取工具

## 文件入口

- 本機啟動與 Linux 部署說明：[docs/STEP_BY_STEP_GUIDE.md](C:/Users/j7johnny/Desktop/20260307CatchingRat/docs/STEP_BY_STEP_GUIDE.md)
- 人工驗收與簡易教學：[docs/MANUAL_ACCEPTANCE_GUIDE.md](C:/Users/j7johnny/Desktop/20260307CatchingRat/docs/MANUAL_ACCEPTANCE_GUIDE.md)
- 對外交付與外部 Linux 部署手冊：[docs/EXTERNAL_HANDOFF_AND_DEPLOYMENT.md](C:/Users/j7johnny/Desktop/20260307CatchingRat/docs/EXTERNAL_HANDOFF_AND_DEPLOYMENT.md)

## 部署輔助檔

- 正式環境 env 範例：[.env.production.example](C:/Users/j7johnny/Desktop/20260307CatchingRat/.env.production.example)
- Linux 自動部署腳本：[scripts/deploy_linux.sh](C:/Users/j7johnny/Desktop/20260307CatchingRat/scripts/deploy_linux.sh)

## 本機測試網址

- 登入頁：[http://localhost:18080/login](http://localhost:18080/login)
- 首次開站設定：[http://localhost:18080/setup/](http://localhost:18080/setup/)
- 友善管理後台：[http://localhost:18080/manage/](http://localhost:18080/manage/)
- 進階 Django admin：[http://localhost:18080/admin/](http://localhost:18080/admin/)
- 浮水印提取頁：[http://localhost:18080/manage/tools/watermark-extract/](http://localhost:18080/manage/tools/watermark-extract/)

## 管理員快速使用教學

### 1. 建立第一個管理員

如果是全新站台，建議直接打開：

[http://localhost:18080/setup/](http://localhost:18080/setup/)

依畫面建立第一位管理者。建立完成後會自動進入友善後台。

如果你偏好 CLI，也可以手動建立：

PowerShell:

```powershell
Set-Location C:\Users\j7johnny\Desktop\20260307CatchingRat
docker compose exec web python manage.py createsuperuser
```

cmd:

```cmd
cd /d C:\Users\j7johnny\Desktop\20260307CatchingRat
docker compose exec web python manage.py createsuperuser
```

CLI 建立完成後，用這個帳號登入 [友善管理後台](http://localhost:18080/manage/)。

### 2. 新增閱讀者帳號

1. 進入 [友善管理後台](http://localhost:18080/manage/)。
2. 點 `閱讀者管理`。
3. 點 `新增閱讀者`。
3. 填入：
   - `帳號`：閱讀者登入 ID，限 `A-Z a-z 0-9 _ . -`，最長 16 字
   - `初始密碼`
   - `帳號啟用`
4. 視需要勾選：
   - `授權全站小說與章節`
   - `授權指定小說`
   - `授權指定章節`
5. 儲存。

這個帳號就是讀者登入用的帳號，也會被寫入隱藏浮水印。

### 3. 建立小說

1. 進入 `小說與章節`。
2. 點 `新增小說`。
3. 填入：
   - `小說名稱`
   - `小說代稱`
   - `簡介`
   - `小說啟用`
4. 儲存。

### 4. 建立章節

1. 進入某本小說的管理頁，或直接點 `新增章節`。
3. 選擇所屬小說。
4. 填入：
   - `章節標題`
   - `章節代稱`
   - `章節排序`
   - `章節全文`
5. 如有需要，可指定 `Anti-OCR 參數集`。
6. 可先按 `儲存草稿`。

### 5. 發布章節

章節儲存後，在章節編輯頁按 `立即發布`，或在小說頁章節列表按 `重新發布`。

發布後系統會：

- 建立新的章節版本
- 產生 desktop / mobile 基底 anti-OCR 圖
- 讓讀者可進入閱讀

如果你更新章節內容後再次發布，系統會建立新版本並讓舊圖片失效。

### 6. 授權閱讀者

目前支援 3 種授權方式：

- 全站授權
- 指定小說授權
- 指定章節授權

設定方式：

1. 進入 `閱讀者管理`。
2. 打開某個閱讀者帳號。
3. 在同一頁的授權區塊中勾選：
   - `授權全站小說與章節`
   - `授權指定小說`
   - `授權指定章節`
4. 儲存閱讀者設定。

### 7. 讀者開始閱讀

1. 讀者到 [登入頁](http://localhost:18080/login) 登入。
2. 先看到「小說列表」。
3. 點入某本小說後可看到該讀者有權限的章節。
4. 點入章節後，系統會依裝置與帳號產生當日個人化浮水印圖片。

### 8. 管理員提取浮水印

如果取得疑似外流圖片：

1. 到 [浮水印提取頁](http://localhost:18080/manage/tools/watermark-extract/)
2. 上傳圖片
3. 系統會嘗試提取 `reader_id|yyyymmdd`

### 9. 建議的管理流程

建議每次都照這個順序：

1. 新增閱讀者
2. 建立小說
3. 建立章節
4. 發布章節
5. 設定授權
6. 用讀者帳號登入驗證
7. 抽查浮水印提取

## Docker 常用指令

PowerShell:

```powershell
Set-Location C:\Users\j7johnny\Desktop\20260307CatchingRat
docker compose up -d
docker compose ps
```

cmd:

```cmd
cd /d C:\Users\j7johnny\Desktop\20260307CatchingRat
docker compose up -d
docker compose ps
```
