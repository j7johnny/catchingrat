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
- 管理後台：[http://localhost:18080/admin/](http://localhost:18080/admin/)
- 浮水印提取頁：[http://localhost:18080/admin/watermark/extract](http://localhost:18080/admin/watermark/extract)

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
