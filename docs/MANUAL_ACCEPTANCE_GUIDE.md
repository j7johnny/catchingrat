# CatchingRat 人工驗收操作手冊

這份文件以「系統已被清回首次啟動狀態」為前提撰寫。  
也就是說：

- 沒有任何現成管理者
- 沒有任何閱讀者
- 沒有任何小說與章節
- 你需要從 `/setup/` 開始建立第一位管理者

## 1. 啟動服務

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

預期：

- `web`
- `worker`
- `beat`
- `nginx`
- `postgres`
- `redis`

都顯示 `Up`。

網站入口：

- 首次啟動：[http://localhost:18080/setup/](http://localhost:18080/setup/)
- 登入頁：[http://localhost:18080/login](http://localhost:18080/login)
- 管理後台：[http://localhost:18080/manage/](http://localhost:18080/manage/)

## 2. 建立第一位管理者

1. 打開 [http://localhost:18080/setup/](http://localhost:18080/setup/)
2. 建立第一位管理者帳號
3. 建立完成後應自動可登入後台
4. 再次打開 `/setup/` 應回 `404`

驗收重點：

- 第一次可正常建立管理者
- 建立後 `/setup/` 會永久關閉

## 3. 管理後台整體導覽

管理者登入後，先確認以下頁面都可正常打開：

- `/manage/`
- `/manage/readers/`
- `/manage/novels/`
- `/manage/settings/anti-ocr/`
- `/manage/settings/anti-ocr/fonts/`
- `/manage/tools/anti7ocr-diagnostics/`
- `/manage/tools/watermark-extract/`
- `/manage/tools/visible-watermark-extract/`

驗收重點：

- 沒有 `403`
- 沒有 `500`
- 頁面可正常顯示表單與按鈕

## 4. 檢查 anti7ocr 預設參數

打開 [http://localhost:18080/manage/settings/anti-ocr/](http://localhost:18080/manage/settings/anti-ocr/)

確認預設 preset 方向：

- `base preset` 為 `tw_readable`
- 不使用「部分字元轉拼音」
- 不使用「中文字倒轉／旋轉」
- Desktop 寬度為 `600`
- Mobile 寬度為 `420`
- 輸出格式為 `PNG`

## 5. 產生 anti7ocr 示範圖片

進入 anti7ocr 設定頁或診斷頁：

1. 輸入一段 100 字以上繁中內容
2. 選擇 preset
3. 分別測一次 `desktop` 與 `mobile`
4. 送出

預期：

- 成功產生示範圖片
- 顯示 OCR 結果
- 顯示 CER
- 可以看出這是一張 anti7ocr 生成圖

## 6. 上傳客製字體

打開 [http://localhost:18080/manage/settings/anti-ocr/fonts/](http://localhost:18080/manage/settings/anti-ocr/fonts/)

建議使用：

- `ttf`
- `otf`
- `ttc`
- `otc`

操作：

1. 輸入字體名稱
2. 上傳字型檔
3. 儲存
4. 回到 anti7ocr 預設頁，確認可選到這個字體

預期：

- 字體上傳成功
- 後續預設與診斷頁可選用該字體

## 7. 建立小說

打開 `/manage/novels/`

1. 建立新小說
2. 填寫標題
3. 填寫 slug
4. 可選填簡介
5. 儲存

預期：

- 小說建立成功
- 可進入該小說詳情頁

## 8. 建立章節並發布

在小說詳情頁中新增章節：

1. 建立章節
2. 填寫標題、slug、排序
3. 貼入長文本
   - 建議至少 1200 字以上
   - 建議用足夠長的內容，方便測多頁圖片與截圖提取
4. 選擇 anti7ocr preset
5. 先按一次「儲存草稿」
6. 再按一次「立即發布」

驗收重點：

- 發布不是瞬間完成，而是等基底圖產完後才算發布成功
- 發布完成前，讀者不應看到該章節
- 發布完成後，章節應可被授權閱讀

## 9. 新增閱讀者並設定授權

打開 `/manage/readers/`

建立一個測試閱讀者，例如：

- 帳號：`reader01`
- 密碼：你自己設定

授權請至少驗證三種情境：

### A. 全站授權

- 勾選全站授權
- 閱讀者應能看到全部小說與章節

### B. 指定小說授權

- 取消全站授權
- 只勾某一本小說
- 閱讀者只能看到那本小說

### C. 指定章節授權

- 取消小說授權
- 只勾某一章
- 閱讀者只看到那一章

## 10. 讀者端閱讀驗收

閱讀者登入後：

1. 應先看到「小說列表」
2. 點入小說後才看到章節列表
3. 點入章節時要先看到 Loading
4. 圖片應逐步載入
5. 若尚未載完，頁面底部應有持續載入提示
6. 按鈕「上一章 / 下一章 / 回章節列表」應可使用

驗收重點：

- 圖片之間應接近無縫連續閱讀
- 快速往下捲不應卡死
- 回到書庫不應異常變慢
- 同章節同日重開應比首次更快

## 11. 閱讀防下載基本保護

在章節閱讀頁驗收：

- 右鍵圖片
- 嘗試拖曳圖片
- 嘗試 `Ctrl+S`
- 嘗試 `Ctrl+P`
- 嘗試 `Ctrl+U`

預期：

- 會有基本阻擋
- 但這不是絕對防護，只是降低直接下載難度

## 12. blind watermark 提取驗收

打開 [http://localhost:18080/manage/tools/watermark-extract/](http://localhost:18080/manage/tools/watermark-extract/)

建議做兩種測試：

### A. 原圖測試

1. 在閱讀頁打開某張 PNG
2. 直接另存那張圖片
3. 回後台上傳到 blind watermark 提取工具

預期：

- 能提取出 `reader_id|yyyymmdd`
- 頁面會顯示提取過程與結果

### B. 長截圖測試

1. 在閱讀頁讓 2 到 3 張圖片連續顯示
2. 用截圖工具做一張長截圖
3. 上傳到 blind watermark 提取工具

預期：

- 在近期快取仍存在時，應能提取成功
- 頁面會顯示使用了哪種方法

## 13. 可見浮水印提取驗收

打開 [http://localhost:18080/manage/tools/visible-watermark-extract/](http://localhost:18080/manage/tools/visible-watermark-extract/)

建議做三種測試：

### A. 原圖提取

1. 上傳瀏覽器直接下載的閱讀 PNG

預期：

- 成功提取 `reader_id|yyyymmdd`

### B. 單頁截圖提取

1. 在閱讀頁對一張頁圖做一般截圖
2. 上傳到可見浮水印提取工具

預期：

- 成功提取 `reader_id|yyyymmdd`

### C. 1 到 3 張連續畫面截圖

1. 在閱讀頁讓 1 到 3 張圖連續顯示
2. 做一張一般截圖或長截圖
3. 上傳到可見浮水印提取工具

預期：

- 在目前版本下，應能成功提取 `reader_id|yyyymmdd`
- 頁面會顯示提取階段、視窗、OCR 嘗試與耗時

## 14. 密碼與防暴力破解

### 讀者修改密碼

1. 以閱讀者登入
2. 進修改密碼頁
3. 用舊密碼改成新密碼
4. 登出再登入

預期：

- 新密碼可用
- 舊密碼失效

### 防暴力破解

1. 故意對同一帳號輸錯多次密碼
2. 觀察是否進入冷卻或鎖定

預期：

- 在設定門檻後會出現限制

## 15. 驗收完成後常用指令

### 查看 log

PowerShell:

```powershell
Set-Location C:\Users\j7johnny\Desktop\20260307CatchingRat
docker compose logs -f
```

cmd:

```cmd
cd /d C:\Users\j7johnny\Desktop\20260307CatchingRat
docker compose logs -f
```

### 停止服務

PowerShell:

```powershell
Set-Location C:\Users\j7johnny\Desktop\20260307CatchingRat
docker compose down
```

cmd:

```cmd
cd /d C:\Users\j7johnny\Desktop\20260307CatchingRat
docker compose down
```
