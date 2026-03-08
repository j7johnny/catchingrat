# CatchingRat 人工驗收指南

這份文件用來手動驗收目前版本的 4 個重點：

1. 章節發布必須等桌機版與手機版基底圖都產生完成，讀者才看得到。
2. `anti7ocr` 設定頁已改成較易懂的分組式表單，且可直接產生示範圖片。
3. 後台可上傳客製字體，並讓 `anti7ocr` 正式發布與示範圖共用。
4. blind watermark 提取可先做全圖，再做大量裁切搜尋，且會留下過程紀錄。

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

預期容器：

- `web`
- `worker`
- `beat`
- `nginx`
- `postgres`
- `redis`

全部都應為 `Up`。

網站入口：

- 首頁：[http://localhost:18080/](http://localhost:18080/)
- 管理後台：[http://localhost:18080/manage/](http://localhost:18080/manage/)
- Django admin：[http://localhost:18080/admin/](http://localhost:18080/admin/)

## 2. 首次開站或既有環境

### 如果是全新環境

1. 打開 [http://localhost:18080/setup/](http://localhost:18080/setup/)
2. 建立第一位管理者
3. 完成後應自動進入 `/manage/`
4. 再次打開 `/setup/` 應回 `404`

### 如果已經有管理者

1. 打開 [http://localhost:18080/login](http://localhost:18080/login)
2. 以管理者帳號登入
3. 應自動導向 [http://localhost:18080/manage/](http://localhost:18080/manage/)

## 3. 管理後台整體驗收

### 3.1 儀表板

進入 `/manage/` 後檢查：

- 側邊欄有固定的 5 個入口：
  - 管理首頁
  - 閱讀者管理
  - 小說與章節
  - anti7ocr 設定
  - 工具
- 頁面右下角或頁尾顯示版本號
- 側邊欄顯示字體庫摘要
- 有 Django admin 備援連結

### 3.2 閱讀者管理

進入 `/manage/readers/`：

1. 新增一個閱讀者
2. 設定密碼
3. 檢查同一頁可直接設定三層授權：
   - 全站授權
   - 指定小說授權
   - 指定章節授權
4. 儲存後再次進入該閱讀者頁面，確認資料仍存在

預期：

- 頁面文字以繁中顯示
- 欄位分組清楚
- 密碼、啟用狀態、授權都在同頁完成

## 4. anti7ocr 設定頁驗收

進入 [http://localhost:18080/manage/settings/anti-ocr/](http://localhost:18080/manage/settings/anti-ocr/)

### 4.1 設定列表

檢查：

- 看到設定卡片而不是難懂的原始模型列表
- 每張卡片可看出是否為預設
- 可直接進入編輯頁
- 可看到字體庫入口

### 4.2 設定編輯頁

打開任一設定或新增設定，檢查分組區塊是否清楚：

- 基本資料
- 文字保護
- 桌機版面
- 手機版面
- 背景與色彩
- 碎裂效果
- 細部擾動
- 輸出

檢查以下預設值是否合理：

- `base preset = tw_readable`
- `啟用局部拼音 = 關閉`
- `拼音比例 = 0`
- `啟用倒字/翻轉 = 關閉`
- `倒字比例 = 0`
- `桌機寬度 = 600`
- `手機寬度 = 420`
- `桌機字級 = 22 ~ 28`
- `手機字級 = 20 ~ 24`
- `輸出格式 = PNG`

### 4.3 產生示範圖片

在 anti7ocr 設定編輯頁：

1. 只修改少量欄位，例如：
   - 設定名稱
   - 基底 preset
   - 示範文字
   - 示範裝置
2. 按 `產生示範圖片`

預期：

- 頁面不會因未填滿所有細部欄位而報錯
- 右側會顯示示範圖片
- 會顯示 seed
- 不會因為只做預覽就真的新增一份 preset

## 5. 客製字體上傳驗收

進入 [http://localhost:18080/manage/settings/anti-ocr/fonts/](http://localhost:18080/manage/settings/anti-ocr/fonts/)

準備一個字體檔，例如：

- `ttf`
- `otf`
- `ttc`
- `otc`

操作：

1. 填入字體名稱
2. 上傳字體檔
3. 保持 `立即啟用` 勾選
4. 送出

預期：

- 上傳成功後回到字體列表
- 該字體顯示為啟用中
- 之後在 anti7ocr 設定頁右側可看到它出現在目前可用字體列表

可再做一次：

1. 按停用
2. 再按啟用
3. 最後按刪除

預期：

- 三個動作都能成功
- 字體摘要數量會跟著更新

## 6. 發布流程驗收

這一段用來驗證「先產出基底圖，完成後才算發布」。

### 6.1 建立小說

進入 `/manage/novels/`：

1. 新增小說
2. 填入：
   - 小說名稱
   - 小說代稱
   - 簡介
3. 儲存

### 6.2 建立章節草稿

在小說頁：

1. 新增章節
2. 填入：
   - 章節名稱
   - 章節代稱
   - 排序
   - 章節全文
   - anti7ocr 設定
3. 先按 `儲存草稿`

預期：

- 章節狀態仍是草稿
- 讀者尚不可見

### 6.3 正式發布

在章節編輯頁按 `立即發布`

預期：

- 頁面會等待發布完成
- 成功訊息應明確提到：
  - 桌機基底圖已完成
  - 手機基底圖已完成
  - 讀者現在才會看到
- 章節狀態變為已發布
- `current_version` 已建立

驗證方式：

1. 發布完成前不要讓讀者刷新該小說頁
2. 發布成功後再用讀者登入檢查
3. 讀者應只會看到已完成發布的內容

## 7. 讀者端驗收

### 7.1 書庫層級

以閱讀者登入後檢查：

- 書庫先顯示「小說」
- 點進小說後才看到章節
- 不再把所有小說與章節擠在同一頁

### 7.2 章節閱讀體驗

打開任一已授權章節後檢查：

- 一開始有 Loading 畫面
- 圖片是連續流式閱讀，切片之間沒有明顯縫隙
- 快速往下拉時，後續圖片仍會持續補載
- 若還沒載完，頁尾會持續顯示載入中的提示
- 頁底有置中的：
  - 上一章
  - 下一章
  - 回章節列表

### 7.3 前端基本防下載

在章節閱讀頁檢查：

- 圖片右鍵功能被阻擋
- 圖片不可拖曳
- `Ctrl+S` / `Ctrl+P` / `Ctrl+U` 有基本阻擋

注意：

- 這只是基本防護，不代表能防止截圖

## 8. 授權驗收

請用同一位閱讀者分 3 次測試：

### A. 全站授權

- 應能看到全部已發布小說與章節

### B. 指定小說授權

- 只能看到被授權小說
- 同小說內已發布章節可見

### C. 指定章節授權

- 只能看到被授權章節
- 未授權章節不可直接打開

## 9. blind watermark 提取驗收

進入 [http://localhost:18080/manage/tools/watermark-extract/](http://localhost:18080/manage/tools/watermark-extract/)

### 9.1 原圖提取

1. 以閱讀者打開章節
2. 取得其中一張站內原圖
3. 上傳到提取工具

預期：

- 先做全圖提取
- 能得到：
  - `reader_id`
  - `yyyymmdd`
- 紀錄中可看到執行過程

### 9.2 單張截圖提取

1. 對閱讀頁中的單張圖片做截圖
2. 上傳到提取工具

預期：

- 若全圖失敗，系統會改做多次區塊裁切嘗試
- 成功時仍能提取出 `reader_id|yyyymmdd`

### 9.3 長截圖提取

1. 對連續多張圖片做長截圖
2. 上傳到提取工具

預期：

- 系統仍會嘗試從多個局部區塊中找可提取區域
- 成功時仍能解析出正確結果

### 9.4 提取紀錄

打開任一提取紀錄頁，檢查：

- 有狀態：
  - pending
  - running
  - succeeded / failed
- 有方法名稱
- 有耗時
- 有過程 log
- 有最終解析出的帳號與日期

## 10. 回歸驗收

### 10.1 Django admin 備援入口

進入 `/admin/`：

- 管理者可登入
- 能看到 anti7ocr 設定模型
- 能看到字體上傳模型
- 能看到浮水印提取相關資料

### 10.2 修改密碼

以管理者或閱讀者測試：

1. 進入修改密碼頁
2. 修改後重新登入

預期：

- 新密碼可登入
- 舊密碼失效

### 10.3 防暴力破解

故意連續輸入錯誤密碼多次：

- 應出現冷卻或暫時鎖定

## 11. 常用指令

### 查看狀態

PowerShell:

```powershell
Set-Location C:\Users\j7johnny\Desktop\20260307CatchingRat
docker compose ps
```

cmd:

```cmd
cd /d C:\Users\j7johnny\Desktop\20260307CatchingRat
docker compose ps
```

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

## 12. 這份版本的最低驗收標準

以下 8 項都通過，才算這版功能驗收完成：

1. 管理者可登入 `/manage/`
2. anti7ocr 設定頁可正常打開且分組清楚
3. `產生示範圖片` 可成功產圖
4. 客製字體可上傳、啟用、停用、刪除
5. 章節發布完成後，讀者才看得到新版本
6. 讀者可正常進入小說、章節與第一張閱讀圖
7. 原圖可成功提取 blind watermark
8. 提取紀錄會保留方法、耗時與過程 log
## 13. 截圖壓測指令
這一版另外提供了專門驗證截圖提取成功率的指令，會自動把 1 到 3 張已產出的個人化頁圖接成長圖，再做多次隨機裁切，模擬閱讀者實際截圖。

PowerShell:

```powershell
Set-Location C:\Users\j7johnny\Desktop\20260307CatchingRat
docker compose exec -T web python manage.py benchmark_watermark_extraction --reader benchreader --device desktop --date 20260309 --chapter-version-id 6 --trials-per-count 8 --max-pages 3
```

cmd:

```cmd
cd /d C:\Users\j7johnny\Desktop\20260307CatchingRat
docker compose exec -T web python manage.py benchmark_watermark_extraction --reader benchreader --device desktop --date 20260309 --chapter-version-id 6 --trials-per-count 8 --max-pages 3
```

參數說明：
- `--reader`：要驗證的閱讀者帳號
- `--device`：`desktop` 或 `mobile`
- `--date`：日快取日期，格式 `YYYYMMDD`
- `--chapter-version-id`：指定某一個章節版本
- `--trials-per-count`：每種頁數組合要跑幾次隨機裁切
- `--max-pages`：最多模擬幾張連續頁面，目前建議 `3`

判讀方式：
- `1 page(s) / 2 page(s) / 3 page(s)` 代表模擬單頁、兩頁、三頁連續截圖
- `success` 越高越好，正式驗收建議至少觀察 5 到 10 次
- `method` 若顯示 `近期單頁...` 或 `近期連續...`，代表這次是透過來源對位成功定位到對應的個人化頁圖
