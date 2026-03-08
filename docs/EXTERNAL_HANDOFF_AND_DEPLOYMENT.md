# CatchingRat 對外交付與 Linux 部署手冊

這份文件是給「接手部署的人」看的。

適用情境：

- 你要把這套網站交給別人部署到外部 Linux 主機
- 對方會透過 SSH 操作主機
- 對方不一定熟悉 Django，但至少能照著指令做

---

## 1. 先講結論：你要交給對方什麼

分成兩種情境。

### 情境 A：只交程式，讓對方自己建立空白站台

你要提供：

- 整個專案原始碼資料夾
- 一份可用的 `.env` 範本
- 這份部署文件

這種方式部署後：

- 網站會啟動
- 但不會包含你目前的小說、章節、讀者帳號、既有圖片快取

### 情境 B：把你目前這一套完整內容一起交出去

你要提供：

- 整個專案原始碼資料夾
- 正式環境用的 `.env`
- PostgreSQL 資料庫匯出檔
- `media` 檔案匯出檔
- 這份部署文件

這種方式部署後：

- 帳號、小說、章節、發布版本、授權、稽核紀錄會一起過去
- 已產生的圖片檔也能一起過去

---

## 2. 哪些檔案應該交，哪些不應該交

### 建議直接交出去的檔案

直接提供整個專案資料夾即可，包含：

- [manage.py](C:/Users/j7johnny/Desktop/20260307CatchingRat/manage.py)
- [requirements.txt](C:/Users/j7johnny/Desktop/20260307CatchingRat/requirements.txt)
- [Dockerfile](C:/Users/j7johnny/Desktop/20260307CatchingRat/Dockerfile)
- [docker-compose.yml](C:/Users/j7johnny/Desktop/20260307CatchingRat/docker-compose.yml)
- [config](C:/Users/j7johnny/Desktop/20260307CatchingRat/config)
- [accounts](C:/Users/j7johnny/Desktop/20260307CatchingRat/accounts)
- [library](C:/Users/j7johnny/Desktop/20260307CatchingRat/library)
- [reader](C:/Users/j7johnny/Desktop/20260307CatchingRat/reader)
- [templates](C:/Users/j7johnny/Desktop/20260307CatchingRat/templates)
- [static](C:/Users/j7johnny/Desktop/20260307CatchingRat/static)
- [docker](C:/Users/j7johnny/Desktop/20260307CatchingRat/docker)
- [docs](C:/Users/j7johnny/Desktop/20260307CatchingRat/docs)

### 不要交出去的本機暫存或垃圾檔

不要把這些一起打包：

- `.venv/`
- `.venv312/`
- `__pycache__/`
- `db.sqlite3`
- `media/`  
  說明：只有在你不是用 Docker volume，而是把檔案直接存專案資料夾時才需要交。現在這套 Docker 預設不是這樣。
- `staticfiles/`
- `.pytest_cache/`
- `.mypy_cache/`
- `.ruff_cache/`
- `celerybeat-schedule`
- `.coverage`
- `htmlcov/`

### `.env` 要怎麼交

`.env` 不建議跟程式碼一起放在公開 Git 倉庫。

建議：

- 用加密通訊單獨傳給部署人員
- 或由部署人員在 Linux 主機上手動建立

---

## 3. 如果你要把「現有內容」一起交出去，還要另外準備什麼

如果你希望對方部署完後，直接就有：

- 管理員帳號
- 讀者帳號
- 小說與章節
- 授權設定
- 既有 anti-OCR / blind watermark 圖片

那你還要再提供兩個東西：

1. PostgreSQL 匯出檔
2. `media` 匯出檔

---

## 4. 在你目前這台 Windows 電腦上，如何整理交付包

以下假設你目前專案在：

`C:\Users\j7johnny\Desktop\20260307CatchingRat`

### 4-1. 建議做法

建議做一個新的交付資料夾，例如：

`C:\Users\j7johnny\Desktop\CatchingRat_Handoff`

內容建議長這樣：

```text
CatchingRat_Handoff/
  app/
    專案原始碼
  backup/
    postgres_dump.sql
    media.tar.gz
  env/
    .env.production
  README_TO_DEPLOYER.txt
```

### 4-2. 只交程式碼時，最簡單的方式

如果你有用 Git：

- 直接把整個專案推到私有 Git 倉庫
- 再把倉庫網址與 `.env` 提供給對方

如果你沒有用 Git：

- 直接把專案資料夾壓縮成 zip
- 但記得排除上面列出的本機暫存檔

### 4-3. Windows PowerShell：建立原始碼交付包

```powershell
Set-Location C:\Users\j7johnny\Desktop
Remove-Item .\CatchingRat_Handoff -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory .\CatchingRat_Handoff\app | Out-Null
robocopy .\20260307CatchingRat .\CatchingRat_Handoff\app /E /XD .venv .venv312 __pycache__ media staticfiles .pytest_cache .mypy_cache .ruff_cache htmlcov .git /XF .env db.sqlite3 celerybeat-schedule .coverage *.log
```

### 4-4. Windows cmd：建立原始碼交付包

```cmd
cd /d C:\Users\j7johnny\Desktop
if exist CatchingRat_Handoff rmdir /s /q CatchingRat_Handoff
mkdir CatchingRat_Handoff\app
robocopy 20260307CatchingRat CatchingRat_Handoff\app /E /XD .venv .venv312 __pycache__ media staticfiles .pytest_cache .mypy_cache .ruff_cache htmlcov .git /XF .env db.sqlite3 celerybeat-schedule .coverage *.log
```

`robocopy` 回傳非 0 不一定代表失敗，只要沒有大量錯誤通常是正常的。

---

## 5. 如果要一起交付現有資料，如何匯出

以下步驟假設你目前網站就是用這個專案的 Docker Compose 在跑。

### 5-1. 匯出 PostgreSQL

PowerShell:

```powershell
Set-Location C:\Users\j7johnny\Desktop\20260307CatchingRat
New-Item -ItemType Directory .\handoff-backup -Force | Out-Null
docker compose exec -T postgres pg_dump --clean --if-exists --no-owner --no-privileges -U catchingrat -d catchingrat > .\handoff-backup\postgres_dump.sql
```

cmd:

```cmd
cd /d C:\Users\j7johnny\Desktop\20260307CatchingRat
if not exist handoff-backup mkdir handoff-backup
docker compose exec -T postgres pg_dump --clean --if-exists --no-owner --no-privileges -U catchingrat -d catchingrat > handoff-backup\postgres_dump.sql
```

如果你有改 `.env` 裡的資料庫帳號或資料庫名稱，請把 `catchingrat` 改成對應值。

### 5-2. 匯出 `media`

PowerShell:

```powershell
Set-Location C:\Users\j7johnny\Desktop\20260307CatchingRat
docker compose exec -T web sh -c "cd /app/media && tar czf - ." > .\handoff-backup\media.tar.gz
```

cmd:

```cmd
cd /d C:\Users\j7johnny\Desktop\20260307CatchingRat
docker compose exec -T web sh -c "cd /app/media && tar czf - ." > handoff-backup\media.tar.gz
```

### 5-3. 準備正式環境 `.env`

不要直接把你目前本機測試用的 `.env` 原封不動交出去。

至少要改：

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG=0`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CSRF_TRUSTED_ORIGINS`
- `POSTGRES_PASSWORD`
- `WATERMARK_PASSWORD_IMG`
- `WATERMARK_PASSWORD_WM`

可從 [.env.production.example](C:/Users/j7johnny/Desktop/20260307CatchingRat/.env.production.example) 複製一份開始改。

---

## 6. 要交給部署人員的最終清單

### 只部署空白站台

你至少應交：

- 專案原始碼
- `.env.production`
- [docs/EXTERNAL_HANDOFF_AND_DEPLOYMENT.md](C:/Users/j7johnny/Desktop/20260307CatchingRat/docs/EXTERNAL_HANDOFF_AND_DEPLOYMENT.md)

### 部署完整現有站台

你至少應交：

- 專案原始碼
- `.env.production`
- `postgres_dump.sql`
- `media.tar.gz`
- [docs/EXTERNAL_HANDOFF_AND_DEPLOYMENT.md](C:/Users/j7johnny/Desktop/20260307CatchingRat/docs/EXTERNAL_HANDOFF_AND_DEPLOYMENT.md)

---

## 7. 外部 Linux 主機的最低需求

建議規格：

- Ubuntu 24.04 LTS 或 Debian 12
- 至少 2 vCPU
- 至少 4 GB RAM
- 至少 30 GB SSD
- 可 SSH 登入
- 已開放對外網路

如果小說很多、章節很長、同時讀者變多，建議更高：

- 4 vCPU
- 8 GB RAM
- 80 GB SSD 以上

---

## 8. Linux 主機從 0 開始部署：完整步驟

以下步驟都在 Linux 主機上做。

### 8-1. 透過 SSH 連線

在你的 Windows 電腦上：

PowerShell:

```powershell
ssh youruser@your-server-ip
```

cmd:

```cmd
ssh youruser@your-server-ip
```

### 8-2. 安裝 Docker 與 Docker Compose

Ubuntu / Debian：

```bash
sudo apt update
sudo apt install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER
newgrp docker
docker --version
docker compose version
```

### 8-3. 建立部署目錄

```bash
sudo mkdir -p /srv/catchingrat
sudo chown $USER:$USER /srv/catchingrat
cd /srv/catchingrat
```

### 8-4. 把專案上傳到主機

#### 方法 A：從 Git 倉庫抓

```bash
git clone <你的私有倉庫網址> app
cd /srv/catchingrat/app
```

#### 方法 B：從你本機直接上傳

在 Windows 本機執行：

PowerShell:

```powershell
scp -r C:\Users\j7johnny\Desktop\CatchingRat_Handoff\app youruser@your-server-ip:/srv/catchingrat/
```

cmd:

```cmd
scp -r C:\Users\j7johnny\Desktop\CatchingRat_Handoff\app youruser@your-server-ip:/srv/catchingrat/
```

上傳後在 Linux 主機上：

```bash
cd /srv/catchingrat/app
```

### 8-5. 建立正式環境 `.env`

在 Linux 主機上：

```bash
cp .env.example .env
nano .env
```

至少改成像這樣：

```env
DJANGO_SECRET_KEY=請換成至少 50 字元亂數
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=your-domain.com,www.your-domain.com,your-server-ip
DJANGO_CSRF_TRUSTED_ORIGINS=https://your-domain.com,https://www.your-domain.com,http://your-server-ip:18080
POSTGRES_DB=catchingrat
POSTGRES_USER=catchingrat
POSTGRES_PASSWORD=請換成強密碼
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
REDIS_URL=redis://redis:6379/1
CELERY_BROKER_URL=redis://redis:6379/2
CELERY_RESULT_BACKEND=redis://redis:6379/3
ANTI_OCR_FONT_PATH=/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc
WATERMARK_PASSWORD_IMG=請換成新的數字密碼
WATERMARK_PASSWORD_WM=請換成新的數字密碼
WATERMARK_FIXED_LENGTH=32
DAILY_CACHE_RETENTION_DAYS=3
```

### 8-6. 先用預設的 `18080` 啟動測試

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f web
```

如果一切正常，你會看到：

- `web`
- `worker`
- `beat`
- `postgres`
- `redis`
- `nginx`

都在 `Up`

### 8-7. 建立第一個管理員

如果這是空白部署：

```bash
docker compose exec web python manage.py createsuperuser
```

如果你是從現有資料還原，通常不用這步。

### 8-8. 驗證網站是否可開

先用 IP 測試：

```text
http://your-server-ip:18080/login
http://your-server-ip:18080/admin/
```

---

## 9. 如果你要還原目前這台站的資料

這部分只在「你有交 `postgres_dump.sql` + `media.tar.gz`」時需要做。

### 9-1. 把備份檔上傳到 Linux 主機

例如放到：

```bash
/srv/catchingrat/backup
```

建立資料夾：

```bash
mkdir -p /srv/catchingrat/backup
```

從 Windows 上傳：

PowerShell:

```powershell
scp C:\Users\j7johnny\Desktop\20260307CatchingRat\handoff-backup\postgres_dump.sql youruser@your-server-ip:/srv/catchingrat/backup/
scp C:\Users\j7johnny\Desktop\20260307CatchingRat\handoff-backup\media.tar.gz youruser@your-server-ip:/srv/catchingrat/backup/
```

cmd:

```cmd
scp C:\Users\j7johnny\Desktop\20260307CatchingRat\handoff-backup\postgres_dump.sql youruser@your-server-ip:/srv/catchingrat/backup/
scp C:\Users\j7johnny\Desktop\20260307CatchingRat\handoff-backup\media.tar.gz youruser@your-server-ip:/srv/catchingrat/backup/
```

### 9-2. 先啟動空容器

```bash
cd /srv/catchingrat/app
docker compose up -d --build
```

### 9-3. 還原 PostgreSQL

```bash
cat /srv/catchingrat/backup/postgres_dump.sql | docker compose exec -T postgres psql -U catchingrat -d catchingrat
```

這個匯出檔已包含 `--clean --if-exists`，所以可以覆蓋掉先前 migration 建好的空白表。

如果你 `.env` 裡的資料庫名稱或帳號有改，這裡也要跟著改。

### 9-4. 還原 `media`

```bash
cat /srv/catchingrat/backup/media.tar.gz | docker compose exec -T web sh -c "cd /app/media && tar xzf -"
```

### 9-5. 重啟服務

```bash
docker compose restart web worker beat nginx
```

### 9-6. 驗證資料是否真的回來

檢查：

- 管理員是否能登入
- 小說與章節是否存在
- 讀者是否能登入
- 章節圖片是否能正常打開
- 管理後台浮水印提取是否可使用

---

## 10. 如果主機要接正式網域

### 10-1. DNS

先把網域 A 記錄指向主機 IP。

例如：

- `your-domain.com -> 主機 IP`
- `www.your-domain.com -> 主機 IP`

### 10-2. 修改 `.env`

把：

- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CSRF_TRUSTED_ORIGINS`

改成正式網域。

### 10-3. 重啟

```bash
docker compose restart web nginx
```

---

## 11. 如果要改成 80 / 443 對外

目前 [docker-compose.yml](C:/Users/j7johnny/Desktop/20260307CatchingRat/docker-compose.yml) 預設是：

```yaml
ports:
  - "18080:80"
```

如果這台主機沒有其他 Web 服務，可改成：

```yaml
ports:
  - "80:80"
```

改完後：

```bash
docker compose up -d
```

如果主機上已經有另一個 Nginx / Caddy / Traefik，則不要直接改成 `80:80`，避免衝突。那種情況建議：

- 繼續讓本專案跑在 `18080`
- 由外層反向代理轉發到 `127.0.0.1:18080`

---

## 12. HTTPS 建議

正式環境建議一定要有 HTTPS。

最簡單做法：

- 用主機外層 Nginx 或 Caddy 反向代理
- 由外層處理 Let's Encrypt 憑證
- 將外部 `443` 轉發到本專案的 `18080`

這樣你不用進容器內再做一層 TLS。

---

## 13. CDN 建議

你先前的需求是：

- 可預期未來會搭配基本版 CDN
- 但個人化內容不可被 CDN 快取

所以部署時請遵守：

### 可以交給 CDN 快取

- `/static/`

### 不應快取

- `/reader/`
- `/login`
- `/logout`
- `/me/password`
- `/admin/`
- `/media/` 內的個人化閱讀圖

這套程式已對閱讀頁與圖片回傳 `Cache-Control: private, no-store`，但 CDN 規則也要配合。

---

## 14. 日後更新程式怎麼做

如果是 Git 部署：

```bash
cd /srv/catchingrat/app
git pull
docker compose up -d --build
docker compose ps
```

如果是壓縮包部署：

1. 先備份 `.env`
2. 用新檔案覆蓋專案原始碼
3. 執行：

```bash
cd /srv/catchingrat/app
docker compose up -d --build
```

---

## 15. 備份建議

至少備份兩樣：

1. PostgreSQL
2. `media`

### 備份 PostgreSQL

```bash
cd /srv/catchingrat/app
docker compose exec -T postgres pg_dump -U catchingrat -d catchingrat > /srv/catchingrat/backup/postgres_$(date +%F).sql
```

### 備份 `media`

```bash
cd /srv/catchingrat/app
docker compose exec -T web sh -c "cd /app/media && tar czf - ." > /srv/catchingrat/backup/media_$(date +%F).tar.gz
```

---

## 16. 交接時一定要一起說清楚的資訊

你除了給檔案，還要口頭或文字告知對方：

- 目前正式網域是什麼
- 主機 IP 是什麼
- SSH 帳號是什麼
- `.env` 的正式值由誰保管
- 是否要一起還原現有資料
- 第一個管理員帳號由誰建立
- CDN 是否已經接上
- 是否有外層反向代理或 WAF

---

## 17. 最建議的實際交付方式

如果你要把這專案正式交給別人，最穩定的做法是：

1. 提供私有 Git 倉庫或原始碼 zip
2. 分開提供 `.env.production`
3. 如果要保留現況，再提供 `postgres_dump.sql`
4. 再提供 `media.tar.gz`
5. 讓對方照這份文件在新主機還原

這樣最不容易漏東西。

---

## 18. 這份文件對應的專案入口

- 專案入口：[README.md](C:/Users/j7johnny/Desktop/20260307CatchingRat/README.md)
- 本機 / 一般教學：[docs/STEP_BY_STEP_GUIDE.md](C:/Users/j7johnny/Desktop/20260307CatchingRat/docs/STEP_BY_STEP_GUIDE.md)
- 人工驗收文件：[docs/MANUAL_ACCEPTANCE_GUIDE.md](C:/Users/j7johnny/Desktop/20260307CatchingRat/docs/MANUAL_ACCEPTANCE_GUIDE.md)

---

## 19. 要放上 GitHub 時，哪些東西可以公開，哪些不行

### 可以放上 GitHub 的

- 專案程式碼
- Docker 相關檔案
- 文件
- [.env.example](C:/Users/j7johnny/Desktop/20260307CatchingRat/.env.example)
- [.env.production.example](C:/Users/j7johnny/Desktop/20260307CatchingRat/.env.production.example)
- [scripts/deploy_linux.sh](C:/Users/j7johnny/Desktop/20260307CatchingRat/scripts/deploy_linux.sh)

### 不要放上 GitHub 的

- 真正可用的 `.env`
- `postgres_dump.sql`
- `media.tar.gz`
- 任一正式帳號密碼
- 任一 SSH 私鑰
- 雲端主機存取資訊

### 建議的 GitHub 發布步驟

在本機專案目錄：

PowerShell:

```powershell
Set-Location C:\Users\j7johnny\Desktop\20260307CatchingRat
git add .
git commit -m "Prepare public deployment docs and scripts"
git branch -M main
git remote add origin https://github.com/<your-account>/<your-repo>.git
git push -u origin main
```

cmd:

```cmd
cd /d C:\Users\j7johnny\Desktop\20260307CatchingRat
git add .
git commit -m "Prepare public deployment docs and scripts"
git branch -M main
git remote add origin https://github.com/<your-account>/<your-repo>.git
git push -u origin main
```

如果你的 repo 已經有 remote，就不要重複 `git remote add origin`。

---

## 20. CLI agent 直接執行方案

這一段是給能直接操作 Linux shell 的 CLI agent 用的。

### 20-1. 你要先幫 agent 準備好這些

- 專案已經在 Linux 主機上
- 已準備好正式環境 `.env.production`
- 如果要還原現有資料，再另外準備：
  - `postgres_dump.sql`
  - `media.tar.gz`

### 20-2. agent 直接執行的最短命令

如果只是空白部署：

```bash
cd /srv/catchingrat/app
chmod +x scripts/deploy_linux.sh
./scripts/deploy_linux.sh --env-file /srv/catchingrat/env/.env.production
```

如果要還原現有資料：

```bash
cd /srv/catchingrat/app
chmod +x scripts/deploy_linux.sh
./scripts/deploy_linux.sh \
  --env-file /srv/catchingrat/env/.env.production \
  --restore-db /srv/catchingrat/backup/postgres_dump.sql \
  --restore-media /srv/catchingrat/backup/media.tar.gz
```

### 20-3. 這個腳本會做什麼

[scripts/deploy_linux.sh](C:/Users/j7johnny/Desktop/20260307CatchingRat/scripts/deploy_linux.sh) 會：

1. 把指定的 env 檔複製成專案根目錄的 `.env`
2. 執行 `docker compose up -d --build`
3. 如有提供資料庫備份，就自動匯入 PostgreSQL
4. 如有提供 media 備份，就自動還原 `media`
5. 還原後自動重啟 `web` / `worker` / `beat` / `nginx`
6. 最後列出 `docker compose ps`

### 20-4. agent 跑完後仍要人工確認

至少檢查：

- `docker compose ps` 全部服務是否 `Up`
- 登入頁是否可開
- 管理後台是否可開
- 若有還原資料，小說與章節是否存在
- 讀者端章節圖片是否能正常顯示
