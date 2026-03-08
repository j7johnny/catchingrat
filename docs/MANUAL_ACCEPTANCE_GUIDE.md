# CatchingRat 人工驗收與簡易教學

這份文件是給「沒有工程背景的人員」使用的。
目標只有兩個：

1. 把本機 Docker 測試站打開
2. 依照固定順序完成人工驗收

如果你目前已經可以打開網站，直接從「二、人工驗收操作順序」開始即可。

## 一、開始前先確認

### 1. 測試網址

- 讀者 / 管理員登入頁：[http://localhost:18080/login](http://localhost:18080/login)
- 管理後台：[http://localhost:18080/admin/](http://localhost:18080/admin/)
- 浮水印提取頁：[http://localhost:18080/admin/watermark/extract](http://localhost:18080/admin/watermark/extract)

### 2. 測試帳號

- 管理員帳號：`admin`
- 管理員密碼：`AdminPass123!`
- 讀者帳號：`demo01`
- 讀者密碼：`ReaderPass123!`

### 3. 如果網站打不開，先確認 Docker 有正常執行

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

預期結果：

- 會看到 `nginx`、`web`、`worker`、`beat`、`postgres`、`redis`
- 這些服務的狀態應該是 `Up`

### 4. 如果服務沒有啟動

PowerShell:

```powershell
Set-Location C:\Users\j7johnny\Desktop\20260307CatchingRat
docker compose up -d
```

cmd:

```cmd
cd /d C:\Users\j7johnny\Desktop\20260307CatchingRat
docker compose up -d
```

---

## 二、人工驗收操作順序

建議照下面順序測，不要跳步。
全部走完一次，大約 15 到 25 分鐘。

### 步驟 1：確認首頁與登入頁可開啟

1. 用瀏覽器打開 [http://localhost:18080/login](http://localhost:18080/login)

預期結果：

- 可以看到登入頁
- 頁面沒有 403、404、502、500

### 步驟 2：用讀者帳號登入

1. 帳號輸入 `demo01`
2. 密碼輸入 `ReaderPass123!`
3. 按登入

預期結果：

- 成功登入
- 會進入讀者書庫頁

### 步驟 3：確認讀者書庫頁內容

1. 在書庫頁確認是否看到小說 `示範小說`
2. 確認是否看到章節 `第一章 追上來的時間`

預期結果：

- 可以看到至少 1 本小說
- 可以看到至少 1 個可閱讀章節

### 步驟 4：打開章節，確認圖片閱讀正常

1. 點進 `第一章 追上來的時間`
2. 觀察第一張圖片是否正常顯示
3. 往下捲動，確認後續圖片也能載入

預期結果：

- 章節不是純文字，而是圖片形式
- 第一張圖可以正常顯示
- 後續圖片可以繼續載入
- 版面沒有明顯破圖

### 步驟 5：切換 Desktop / Mobile 閱讀版本

1. 在章節頁右上角找到 `Desktop` 和 `Mobile`
2. 先點 `Mobile`
3. 再點回 `Desktop`

預期結果：

- 兩種模式都可切換
- 切換後圖片寬度會有差異
- 兩種模式都能正常閱讀

### 步驟 6：測試讀者修改密碼

1. 在頁面上方點 `修改密碼`
2. 將舊密碼填入 `ReaderPass123!`
3. 新密碼改成 `ReaderPass456!`
4. 再輸入一次 `ReaderPass456!`
5. 送出

預期結果：

- 顯示修改成功
- 沒有跳出錯誤

### 步驟 7：登出後用新密碼重新登入

1. 點頁面上方 `登出`
2. 回到登入頁
3. 使用 `demo01 / ReaderPass456!` 重新登入

預期結果：

- 舊密碼不能再使用
- 新密碼可以成功登入

### 步驟 8：測試簡易防暴力破解

這個步驟不要用正式測試帳號做。
請使用一個假的帳號，例如 `locktest01`。

1. 登出
2. 在登入頁輸入帳號 `locktest01`
3. 密碼任意輸入錯誤值，例如 `wrongpass`
4. 連續送出 5 次
5. 第 6 次再送一次

預期結果：

- 前幾次會顯示帳號或密碼錯誤
- 到達限制後，會顯示暫時鎖定或稍後再試的訊息

補充說明：

- 這個鎖定是針對 `帳號 + IP`
- 因為你用的是假帳號，所以不會影響 `demo01`

### 步驟 9：確認正確帳號仍可登入

1. 回到登入頁
2. 使用 `demo01 / ReaderPass456!` 登入

預期結果：

- 正確帳號仍然可以正常登入

### 步驟 10：用管理員帳號進入後台

建議用另一個瀏覽器，或用無痕視窗操作，避免把讀者登入狀態洗掉。

1. 打開 [http://localhost:18080/admin/](http://localhost:18080/admin/)
2. 使用 `admin / AdminPass123!` 登入

預期結果：

- 可以進入 Django 後台
- 可以看到 `Users`、`Novels`、`Chapters`、`Reader chapter grants` 等資料管理項目

### 步驟 11：確認既有測試資料存在

1. 進入 `Users`
2. 確認有 `admin` 與 `demo01`
3. 進入 `Novels`
4. 確認有 `示範小說`
5. 進入 `Chapters`
6. 確認有 `第一章 追上來的時間`
7. 進入 `Reader chapter grants`
8. 確認 `demo01` 已被授權到該章節

預期結果：

- 測試資料都存在
- 讀者權限已建立

### 步驟 12：測試後台發布章節

1. 在後台進入 `Chapters`
2. 點開 `第一章 追上來的時間`
3. 在 `content` 最後面追加一段容易辨識的文字，例如：

```text
【人工驗收標記】這一段文字是用來確認重新發布後，讀者端已經換成新版本。
```

4. 先按 `Save`
5. 回到 `Chapters` 列表頁
6. 在該章節右側按 `發布`

預期結果：

- 後台顯示發布成功
- 同一章節可重新發布新版本

### 步驟 13：確認讀者端看到新版本

1. 回到讀者視窗
2. 重新進入 `第一章 追上來的時間`
3. 往下滑到最後幾張圖片
4. 確認剛剛新增的 `【人工驗收標記】...` 文字已出現

預期結果：

- 重新發布後，讀者端能看到新版內容
- 閱讀仍以圖片形式呈現

### 步驟 14：測試隱藏浮水印提取

這一步請先從讀者頁面存一張圖片。

1. 在讀者章節頁面，對第一張圖片按滑鼠右鍵
2. 選擇「另存圖片」
3. 把檔案存到桌面，例如 `page1.png`
4. 回到管理後台，打開 [http://localhost:18080/admin/watermark/extract](http://localhost:18080/admin/watermark/extract)
5. 上傳剛剛存下來的 `page1.png`
6. 按送出

預期結果：

- 頁面會顯示解出的內容
- 應該可以看到 `reader_id`
- `reader_id` 應該是 `demo01`
- 日期應該是今天的 `yyyymmdd`

### 步驟 15：可選測試，提取一般截圖

這一步是額外測試，不是最基本的通關條件。

1. 對讀者章節頁做一張一般螢幕截圖
2. 回到浮水印提取頁
3. 上傳截圖檔

預期結果：

- 若截圖品質足夠，應有機會提取出 `demo01|yyyymmdd`
- 如果沒有成功，至少原始站內輸出圖應該可以成功提取

---

## 三、建議的驗收通過標準

如果下面 8 項都成立，就可以視為本機人工驗收通過：

1. 登入頁可以正常開啟
2. 讀者可以成功登入
3. 讀者可以看到授權章節
4. 章節以圖片方式正常閱讀
5. Desktop / Mobile 兩種版本都能切換
6. 讀者可以修改密碼並用新密碼重新登入
7. 後台可以重新發布章節，且讀者端看到新版本
8. 管理員可從閱讀圖片中提取出 `reader_id|yyyymmdd`

---

## 四、驗收完成後建議恢復的內容

如果你有做過密碼修改，建議把讀者測試帳號改回原始值，方便下次驗收。

建議恢復為：

- 讀者帳號：`demo01`
- 讀者密碼：`ReaderPass123!`

如果你有在章節內加入 `【人工驗收標記】...`，也可以在後台刪掉後再重新發布一次。

---

## 五、常用指令

### 查看目前服務狀態

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

### 查看即時 log

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

### 停止本專案

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

### 重新啟動本專案

PowerShell:

```powershell
Set-Location C:\Users\j7johnny\Desktop\20260307CatchingRat
docker compose up -d
```

cmd:

```cmd
cd /d C:\Users\j7johnny\Desktop\20260307CatchingRat
docker compose up -d
```

---

## 六、文件位置

這份文件在：

[docs/MANUAL_ACCEPTANCE_GUIDE.md](C:/Users/j7johnny/Desktop/20260307CatchingRat/docs/MANUAL_ACCEPTANCE_GUIDE.md)
