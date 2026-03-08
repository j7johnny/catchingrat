# CatchingRat Step-by-Step 手冊

這份文件是給「沒有相關背景」的人用的。

你可以把它分成兩種用途：

1. 在 Windows 本機把系統啟動起來做測試
2. 之後透過 SSH 把同一套系統部署到 Linux 雲端主機

---

## 0. 你會得到什麼

這套系統啟動後，你會有：

- 一個管理後台：新增閱讀者、貼入章節、發布章節、授權章節、提取浮水印
- 一個閱讀端：閱讀者登入後可以看到被授權的章節並閱讀
- anti-OCR 圖片輸出
- 隱藏浮水印輸出與提取

---

## 1. Windows 本機測試：推薦做法是 Docker

這是最簡單、最不容易出錯的方式。

### 1-1. 先安裝這些軟體

請先安裝：

- Docker Desktop
- Git

安裝完成後，重新開機一次最保險。

### 1-2. 把專案放到本機

如果你已經有這個資料夾，可以直接跳到下一步。

假設專案放在：

`C:\Users\你的帳號\Desktop\20260307CatchingRat`

### 1-3. 建立 `.env`

在專案根目錄把 `.env.example` 複製成 `.env`

PowerShell:

```powershell
Set-Location C:\Users\你的帳號\Desktop\20260307CatchingRat
Copy-Item .env.example .env
```

cmd:

```cmd
cd /d C:\Users\你的帳號\Desktop\20260307CatchingRat
copy .env.example .env
```

### 1-4. 第一次啟動 Docker

PowerShell:

```powershell
Set-Location C:\Users\你的帳號\Desktop\20260307CatchingRat
docker compose up --build
```

cmd:

```cmd
cd /d C:\Users\你的帳號\Desktop\20260307CatchingRat
docker compose up --build
```

說明：

- 第一次會下載很多映像檔，可能要 5 到 20 分鐘
- 畫面一直滾動是正常的
- 看到類似 `listening on`、`ready`、`worker` 這類訊息通常代表啟動成功

### 1-5. 保持這個視窗不要關

這個視窗一關，服務就會停。

如果你想讓它在背景執行：

PowerShell:

```powershell
docker compose up -d --build
```

cmd:

```cmd
docker compose up -d --build
```

### 1-6. 建立第一個管理員帳號

建議直接打開瀏覽器：

[http://localhost:18080/setup/](http://localhost:18080/setup/)

依畫面建立第一位管理者即可。建立完成後，系統會自動進入友善管理後台 `/manage/`。

如果你偏好用終端機建立，也可以另外開一個視窗執行：

PowerShell:

```powershell
Set-Location C:\Users\你的帳號\Desktop\20260307CatchingRat
docker compose exec web python manage.py createsuperuser
```

cmd:

```cmd
cd /d C:\Users\你的帳號\Desktop\20260307CatchingRat
docker compose exec web python manage.py createsuperuser
```

### 1-7. 打開網站

在瀏覽器打開：

- 網站首頁：`http://localhost`
- Django 直連：`http://localhost:8000`
- 友善管理後台：`http://localhost:18080/manage/`
- 進階 Django admin：`http://localhost:18080/admin/`
- 浮水印提取頁：`http://localhost:18080/manage/tools/watermark-extract/`

---

## 2. Windows 本機測試：第一次進站怎麼操作

### 2-1. 用管理員登入後台

打開：

`http://localhost:18080/manage/`

輸入剛剛建立的管理員帳號。

### 2-2. 建立一個閱讀者帳號

在友善後台進入 `閱讀者管理`

新增一個閱讀者，建議：

- 帳號：`reader01`
- 初始密碼：自行設定
- 帳號啟用：打勾

注意：

- 帳號只接受英數字與 `_ . -`
- 最長 16 字
- 系統會自動轉成小寫

### 2-3. 建立小說

在友善後台進入 `小說與章節`

新增：

- title：小說名稱
- slug：可填英數代稱，例如 `novel-a`

### 2-4. 建立章節

在友善後台進入小說頁後點 `新增章節`

新增：

- novel：選剛才的小說
- title：例如 `第一章`
- slug：例如 `chapter-1`
- sort_order：例如 `1`
- content：把小說正文貼進去

可先按 `儲存草稿`。

### 2-5. 發布章節

儲存後在章節頁按 `立即發布`

系統會：

- 建立章節版本
- 產生 anti-OCR 基底圖
- 之後在閱讀時再產生帶浮水印的每日圖片

### 2-6. 授權這個章節給閱讀者

回到 `閱讀者管理`

打開 `reader01` 後，於授權區塊勾選：

- `授權指定章節`
- 勾選剛才那一章

### 2-7. 用閱讀者登入測試

先登出後台，再打開：

`http://localhost/login`

用剛才建立的 `reader01` 登入。

你應該會看到：

- 我的書庫
- 被授權的小說與章節

點章節後即可閱讀。

### 2-8. 測試浮水印提取

1. 用閱讀者打開章節
2. 把第一張圖片另存或截圖
3. 用管理員打開：

   `http://localhost:18080/manage/tools/watermark-extract/`

4. 上傳圖片
5. 應可看到 `reader_id|yyyymmdd` 對應結果

---

## 3. 本機常用指令

### 啟動

PowerShell:

```powershell
Set-Location C:\Users\你的帳號\Desktop\20260307CatchingRat
docker compose up -d
```

cmd:

```cmd
cd /d C:\Users\你的帳號\Desktop\20260307CatchingRat
docker compose up -d
```

### 停止

PowerShell:

```powershell
docker compose down
```

cmd:

```cmd
docker compose down
```

### 看 log

PowerShell:

```powershell
docker compose logs -f
```

cmd:

```cmd
docker compose logs -f
```

### 重建

PowerShell:

```powershell
docker compose down
docker compose up -d --build
```

cmd:

```cmd
docker compose down
docker compose up -d --build
```

---

## 4. 如果不想用 Docker，本機也可以直接用 Python 啟動

這是備用方案。推薦仍然先用 Docker。

### 4-1. 先安裝

請安裝：

- Python 3.12
- PostgreSQL
- Redis

如果你不熟，這條路通常比 Docker 更容易出錯。

### 4-2. 建立 venv

PowerShell:

```powershell
Set-Location C:\Users\你的帳號\Desktop\20260307CatchingRat
py -3.12 -m venv .venv312
```

cmd:

```cmd
cd /d C:\Users\你的帳號\Desktop\20260307CatchingRat
py -3.12 -m venv .venv312
```

### 4-3. 安裝依賴

PowerShell:

```powershell
.\.venv312\Scripts\python.exe -m pip install -r requirements-dev.txt
```

cmd:

```cmd
.\.venv312\Scripts\python.exe -m pip install -r requirements-dev.txt
```

### 4-4. 建立 `.env`

PowerShell:

```powershell
Copy-Item .env.example .env
```

cmd:

```cmd
copy .env.example .env
```

### 4-5. 修改 `.env`

至少要確認：

- PostgreSQL 連線資訊正確
- Redis 連線資訊正確
- `ANTI_OCR_FONT_PATH` 指到可用中文字型

Windows 常見字型可先試：

- `C:/Windows/Fonts/msjh.ttc`
- `C:/Windows/Fonts/msyh.ttc`

### 4-6. 執行 migration

PowerShell:

```powershell
.\.venv312\Scripts\python.exe manage.py migrate
```

cmd:

```cmd
.\.venv312\Scripts\python.exe manage.py migrate
```

### 4-7. 建立管理員

PowerShell:

```powershell
.\.venv312\Scripts\python.exe manage.py createsuperuser
```

cmd:

```cmd
.\.venv312\Scripts\python.exe manage.py createsuperuser
```

### 4-8. 啟動 Django

PowerShell:

```powershell
.\.venv312\Scripts\python.exe manage.py runserver
```

cmd:

```cmd
.\.venv312\Scripts\python.exe manage.py runserver
```

### 4-9. 啟動 Celery Worker

PowerShell:

```powershell
.\.venv312\Scripts\celery.exe -A config worker -l info
```

cmd:

```cmd
.\.venv312\Scripts\celery.exe -A config worker -l info
```

### 4-10. 啟動 Celery Beat

PowerShell:

```powershell
.\.venv312\Scripts\celery.exe -A config beat -l info
```

cmd:

```cmd
.\.venv312\Scripts\celery.exe -A config beat -l info
```

---

## 5. Linux 雲端部署：建議做法

推薦用一台 Linux 主機 + Docker Compose。

適合：

- Ubuntu 24.04
- Debian 12

---

## 6. Linux 雲端部署前準備

你需要：

- 一台 Linux 雲端主機
- 主機 IP
- SSH 帳號，例如 `ubuntu`
- 一個網域名稱（若未來要用 HTTPS / CDN，建議先有）

---

## 7. 從 Windows 連線到 Linux 主機

PowerShell:

```powershell
ssh ubuntu@你的主機IP
```

cmd:

```cmd
ssh ubuntu@你的主機IP
```

登入後，接下來的指令都是在 Linux 主機裡執行，不分 PowerShell / cmd。

---

## 8. 在 Linux 主機安裝 Docker

下面以 Ubuntu / Debian 為例。

```bash
sudo apt update
sudo apt install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER
```

執行完後：

1. 登出 SSH
2. 重新登入 SSH

然後確認：

```bash
docker --version
docker compose version
```

---

## 9. 把專案放到 Linux 主機

方法很多，最簡單的是 Git clone 或 SFTP 上傳。

### 9-1. 用 Git clone

```bash
cd ~
git clone 你的專案網址 catchingrat
cd catchingrat
```

### 9-2. 如果沒有 Git 倉庫

你也可以用 WinSCP / FileZilla / VS Code Remote SSH 把整個資料夾上傳到：

`~/catchingrat`

---

## 10. 建立 Linux 用的 `.env`

```bash
cd ~/catchingrat
cp .env.example .env
```

然後編輯：

```bash
nano .env
```

至少修改：

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG=0`
- `DJANGO_ALLOWED_HOSTS=你的網域,你的主機IP`
- `POSTGRES_PASSWORD`

`DJANGO_SECRET_KEY` 可用：

```bash
python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(50))
PY
```

---

## 11. 啟動 Linux 版服務

```bash
cd ~/catchingrat
docker compose up -d --build
```

查看狀態：

```bash
docker compose ps
docker compose logs -f
```

---

## 12. 建立雲端管理員

先打開：

`http://你的主機IP/setup/`

或：

`http://你的網域/setup/`

依畫面建立第一位管理者即可。

---

## 13. 開放防火牆

如果你使用 Ubuntu UFW：

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
```

如果你是雲端平台，也要同時在雲端平台的 Security Group / Firewall 開放：

- 22
- 80
- 443

---

## 14. 讓網站可以從外部打開

### 14-1. 先用 IP 測試

在瀏覽器打開：

`http://你的主機IP`

### 14-2. 再接網域

把你的網域 DNS A record 指到主機 IP。

等 DNS 生效後，瀏覽器打開：

`http://你的網域`

---

## 15. HTTPS 建議

正式環境建議一定要上 HTTPS。

最簡單做法：

- 在主機前面再放一層反向代理
- 或使用你熟悉的 CDN / WAF 服務做 TLS 終止

如果你自己在主機上做憑證，可考慮：

- Caddy
- Nginx + Certbot

---

## 16. CDN 設定重點

這個系統有「個人化閱讀圖片」。

所以 CDN 只能快取靜態檔，不可以快取閱讀頁和個人化圖片。

請把 CDN 規則設成：

### 可以快取

- `/static/*`

### 不可快取

- `/reader/*`
- `/media/base_pages/*`
- `/media/daily_pages/*`
- `/admin/*`

如果你用 Cloudflare，概念上就是：

- `static/*` 可以 Cache Everything 或照原站頭快取
- `reader/*`、`media/*`、`admin/*` 一律 Bypass cache

---

## 17. 每次更新程式怎麼做

如果你有 Git：

```bash
cd ~/catchingrat
git pull
docker compose up -d --build
```

如果有 schema 變更，保險做法：

```bash
cd ~/catchingrat
docker compose up -d --build
docker compose exec web python manage.py migrate
```

---

## 18. 常見問題

### 問題 1：`docker compose up --build` 很久都沒結束

第一次下載映像與套件本來就會比較久，先等。

如果超過 20 分鐘還卡住：

- 確認網路正常
- 重新執行一次
- 檢查 Docker Desktop 是否正常啟動

### 問題 2：頁面打不開

請先檢查：

- Docker 是否真的在跑
- `docker compose ps`
- `docker compose logs -f`

### 問題 3：anti-OCR 生成失敗

通常是字型找不到。

先檢查：

- Windows：`C:/Windows/Fonts/msjh.ttc` 是否存在
- Linux：Docker 內 Noto CJK 是否正常安裝
- `.env` 的 `ANTI_OCR_FONT_PATH` 是否正確

### 問題 4：浮水印提取失敗

請先用：

- 站內原圖
- 一般截圖

不要先拿：

- 聊天軟體重壓縮過的圖片
- 手機翻拍螢幕的照片

---

## 19. 建議的實際流程

如果你是第一次接手，請照這個順序做：

1. 先用 Docker 在 Windows 本機跑起來
2. 先建立管理員
3. 建一個閱讀者
4. 建一本小說、一個章節
5. 發布章節
6. 授權章節
7. 用閱讀者登入閱讀
8. 截圖後回後台做浮水印提取
9. 全部確認沒問題後，再上 Linux 雲端

---

## 20. 這份文件對應的專案入口

如果要查看原始設定與程式位置，主要看：

- `README.md`
- `docker-compose.yml`
- `Dockerfile`
- `config/settings.py`
- `library/services/publishing.py`
- `library/services/watermark.py`
