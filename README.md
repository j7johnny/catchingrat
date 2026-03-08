# CatchingRat

封閉式中文長文本閱讀站，技術棧為 `Django 6 + PostgreSQL + Redis + Celery + Nginx + Docker Compose`。

目前版本重點：

- 只有管理者能建立閱讀者帳號，沒有前台註冊
- 管理者貼入章節後，先產生 `anti7ocr` 基底圖，完成後才算發布
- 閱讀者開章時，同時疊加兩層浮水印
  - 可見浮水印：低可見度、經影像處理後可辨識
  - blind watermark：隱藏式浮水印
- 後台可分別提取 `可見浮水印` 與 `blind watermark`
- 首次啟動沒有任何帳號，需先到 `/setup/` 建立第一位管理者

## 主要入口

- 首次啟動建立管理者：[http://localhost:18080/setup/](http://localhost:18080/setup/)
- 登入頁：[http://localhost:18080/login](http://localhost:18080/login)
- 友善管理後台：[http://localhost:18080/manage/](http://localhost:18080/manage/)
- Django admin 備援入口：[http://localhost:18080/admin/](http://localhost:18080/admin/)

## 本機啟動

### PowerShell

```powershell
Set-Location C:\Users\j7johnny\Desktop\20260307CatchingRat
docker compose up -d
docker compose ps
```

### cmd

```cmd
cd /d C:\Users\j7johnny\Desktop\20260307CatchingRat
docker compose up -d
docker compose ps
```

預期 `web`、`worker`、`beat`、`nginx`、`postgres`、`redis` 都顯示 `Up`。

## 第一次使用

1. 打開 [http://localhost:18080/setup/](http://localhost:18080/setup/)
2. 建立第一位管理者帳號
3. 建立完成後系統會關閉 `/setup/`，之後只能透過登入頁進站
4. 管理者登入後會進入 [http://localhost:18080/manage/](http://localhost:18080/manage/)

## 管理者常用操作

### 1. 新增閱讀者

進入 `/manage/readers/`：

1. 建立帳號與密碼
2. 設定是否啟用
3. 選擇授權層級
   - 全站授權
   - 指定小說授權
   - 指定章節授權

### 2. 新增小說與章節

進入 `/manage/novels/`：

1. 建立小說
2. 在小說頁內新增章節
3. 貼入章節全文
4. 選擇 anti7ocr preset
5. 可先儲存草稿，再正式發布

### 3. anti7ocr 設定與預覽

進入 `/manage/settings/anti-ocr/`：

- 可管理 anti7ocr preset
- 可手動產生一張示範圖片
- 可使用診斷工具檢查 OCR 與 CER

診斷工具入口：

- [http://localhost:18080/manage/tools/anti7ocr-diagnostics/](http://localhost:18080/manage/tools/anti7ocr-diagnostics/)

字體上傳入口：

- [http://localhost:18080/manage/settings/anti-ocr/fonts/](http://localhost:18080/manage/settings/anti-ocr/fonts/)

### 4. 浮水印提取工具

blind watermark 提取：

- [http://localhost:18080/manage/tools/watermark-extract/](http://localhost:18080/manage/tools/watermark-extract/)

可見浮水印提取：

- [http://localhost:18080/manage/tools/visible-watermark-extract/](http://localhost:18080/manage/tools/visible-watermark-extract/)

兩個工具都會保留：

- 上傳檔名
- 提取結果
- 使用方法
- 嘗試次數
- 耗時
- 過程紀錄

## 讀者端重點

- 書庫是兩層結構：先小說，再章節
- 點入章節時會先出現 Loading
- 圖片採連續閱讀方式載入
- 頁面有上一章 / 下一章 / 回章節列表
- 圖片有基本防右鍵下載與拖曳保護

## 文件

- 新手本機與 Linux 部署說明：[docs/STEP_BY_STEP_GUIDE.md](C:/Users/j7johnny/Desktop/20260307CatchingRat/docs/STEP_BY_STEP_GUIDE.md)
- 人工驗收與操作教學：[docs/MANUAL_ACCEPTANCE_GUIDE.md](C:/Users/j7johnny/Desktop/20260307CatchingRat/docs/MANUAL_ACCEPTANCE_GUIDE.md)
- 外部交接與部署：[docs/EXTERNAL_HANDOFF_AND_DEPLOYMENT.md](C:/Users/j7johnny/Desktop/20260307CatchingRat/docs/EXTERNAL_HANDOFF_AND_DEPLOYMENT.md)

## 常用 Docker 指令

### PowerShell

```powershell
Set-Location C:\Users\j7johnny\Desktop\20260307CatchingRat
docker compose logs -f
docker compose down
```

### cmd

```cmd
cd /d C:\Users\j7johnny\Desktop\20260307CatchingRat
docker compose logs -f
docker compose down
```
