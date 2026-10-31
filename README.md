# 研究報告儀表板

市場調查、流量情報、人物研究、事件追蹤、平台研究、生活熱點——所有研究報告累積在一個頁面，點開即是全文，向下捲動一目瞭然。

- **線上儀表板（繁體）**：https://alexchiachi.github.io/research-dashboard/
- **線上儀表板（簡體）**：https://alexchiachi.github.io/research-dashboard/zh-cn/
- **每日社群流量 Top10（互動版）**：https://alexchiachi.github.io/research-dashboard/traffic.html
- **每週生活熱點全歸檔**：https://alexchiachi.github.io/research-dashboard/weekly/
- **內容來源**：Google Drive「研究報告庫」（六大分類歸檔，含雲端原檔雙向同步）
- **核心架構**：報告資料（Markdown/JSON）與視覺樣板（Template）解耦，透過 `build.py` 一鍵自動編譯。

---

## 🛠 環境需求與套件安裝

在初次運行或新機器環境下，請先確保已安裝以下 Python 相依套件：

```bash
pip3 install markdown opencc-python-reimplemented
```

* **`markdown`**：負責將 Markdown 內文轉換為符合標準規範的 HTML（支援表格 `tables` 與代碼塊 `fenced_code`）。
* **`opencc-python-reimplemented`**：負責透過 `tw2sp` 字典自動將繁體版轉換為大陸在地用語簡體版（如：程式碼 ➔ 代码、軟體 ➔ 软件）。未安裝時將自動略過簡體版生成。
* **`gdrive` CLI**：負責與 Google 雲端硬碟雙向同步，請確保已登入授權（執行 `gdrive auth status` 確認）。

---

## 🗂 目錄結構

```text
research-dashboard/
├── reports/                 # 獨立報告存放庫（按分類歸檔）
│   ├── 01_market/           # 01 市場調查
│   ├── 02_traffic/          # 02 流量情報（解耦數據架構）
│   │   ├── daily/*.json     # 每日七地情報結構化數據（台/中/日/韓/美/歐/中東 各 10 則）
│   │   ├── daily_md/*.md    # 每日自動生成的完整 Markdown 簡報庫
│   │   ├── data.json        # 每日流量編譯匯總資料快取
│   │   └── *.md             # 歷史綜合與每週流量模式摘要報告
│   ├── 03_people/           # 03 人物研究
│   ├── 04_events/           # 04 事件追蹤
│   ├── 05_platform/         # 05 平台研究
│   └── 06_weekly/           # 06 生活熱點 × 社會創新（37 期雙語原檔與 manifest）
│       ├── manifest.json
│       └── raw/*.md
├── traffic.html             # 每日社群流量 Top10 獨立互動儀表板（支援七地切換與紙墨美學）
├── weekly/                  # 生活熱點 × 社會創新專屬全歸檔頁（繁體）
├── zh-cn/weekly/            # 生活熱點 × 社會創新專屬全歸檔頁（簡體）
├── sync_traffic_to_gdrive.py# 每日流量情報 Google 雲端硬碟雙軌同步腳本
├── build_traffic.py         # 每日流量編譯模組（讀取 daily/，編譯 data.json 並注入 traffic.html）
├── sync_weekly.py           # Google Drive 雲端熱點文件自動同步腳本
├── weekly_parser.py         # 雙語段落與熱點標題智慧解析器
├── weekly_template.html     # 熱點專屬母樣板（含中英切換、月份導覽與防孤字）
├── build_weekly.py          # 熱點獨立頁建置模組
├── template.html            # 儀表板視覺與互動母樣板（含紙墨美學、防孤字、搜尋與折疊控制）
├── build.py                 # 一鍵整合編譯腳本（自動串接 weekly、traffic、主頁、簡體版與 Sitemap）
├── index.html               # 繁體版發布產物（含 hreflang 與「简体」切換鈕）
├── zh-cn/
│   └── index.html           # 簡體版發布產物（含 Noto SC 字型與「繁体」切換鈕）
├── sitemap.xml              # 雙語系 Sitemap（含主頁、weekly 與 traffic.html）
├── robots.txt               # 爬蟲宣告
└── README.md
```

---

## 🔄 每日流量情報運作 SOP（七地情報自轉）

系統每日監測涵蓋 **台灣 · 中國 · 日本 · 韓國 · 美國 · 歐洲 · 中東** 七大區域，每日共 70 則焦點（每地 5 則綜合 + 5 則生活類）。

### 1. 數據結構規範 (`reports/02_traffic/daily/YYYY-MM-DD.json`)
檔案必須包含以下結構化契約，確保前端與雲端正常渲染：
* `date`: 日期字串（`YYYY-MM-DD`）
* `globalTheme`: 今日全球主線（核心定錨）
* `globalSummary`: 今日人心觀察（深度社會心理與情緒耗散結構）
* `storylines`: 跨區故事線陣列（`[{ id, kind, title, summary, items }]`）
* `suggestions`: 大道至簡三大專欄選題（《金融一百零八講》、《俗人對話錄》、《佛法生活感悟文》）
* `events`: 七地情報陣列，共 70 則（包含 `id`, `rank` (1-5), `category` ("綜合"|"生活"), `region` ("台灣"|"中國"|"日本"|"韓國"|"美國"|"歐洲"|"中東"), `title`, `summary`, `sourceUrl`, `brandRelevant`）

### 2. Google 雲端雙軌同步
```bash
python3 sync_traffic_to_gdrive.py YYYY-MM-DD
```
* **功能**：
  1. 自動生成高質感排版報告 `reports/02_traffic/daily_md/YYYY-MM-DD-traffic.md`。
  2. 自動將 Markdown 簡報與原始 JSON 檔案同步上傳至 Google 雲端硬碟「02_流量情報」專屬資料夾（ID: `1467YTUDdUK-mlXkddfbN7QhWRGWzBTw_`）。

### 3. 一鍵本地編譯
```bash
python3 build.py
```
* `build.py` 內部會自動串接 `build_traffic.py`，將 `daily/*.json` 依日期遞減排序匯總至 `data.json`，並安全注入至 `traffic.html`。

---

## 🔄 如何同步「每週生活熱點 × 社會創新」

當 Google Drive 雲端硬碟累積了新的熱點週報時：
```bash
# 1. 自動從雲端硬碟匯出新期數（增量下載）
python3 sync_weekly.py

# 2. 一鍵編譯主頁與全歸檔獨立頁（繁簡雙版本）
python3 build.py
```

---

## 🚀 如何新增一份常規研究報告

1. 在 `reports/` 對應分類資料夾建立新的 `.md` 檔案（例如 `reports/01_market/2026-10-25-new-topic.md`）。
2. 在檔案頂部加入 YAML Frontmatter 標頭：
   ```markdown
   ---
   id: "r-new-topic"
   title: "報告完整標題"
   date: "2026-10-25"
   category: "01_market"
   tag: "深度報告"
   point: "一句話核心結論摘要。"
   drive_url: "https://drive.google.com/..."
   search: "關鍵字 搜尋標籤 分類詞"
   ---

   ## 一、核心結論
   此處撰寫報告正文，支援標準 Markdown 語法與自訂 HTML...
   ```
3. **編譯器自動化特性**：
   * **閱讀時間計算**：`build.py` 會自動統計中文（380 字/分）與英文單詞，自動產生預估閱讀分鐘數。
   * **篇內目錄 (Mini-TOC)**：章節標題超過 3 個時，自動產生折疊式導覽清單。
   * **表格防破版**：自動替所有 `<table>` 包覆水平捲動外框。
   * **標題日期清理**：自動移除標題尾部的 `（YYYY-MM-DD）`，保持側邊導覽簡潔。
4. 在專案根目錄執行編譯：
   ```bash
   python3 build.py
   ```

---

## 🤖 自動化排程機制 (Antigravity 2.0 Sidecars)

專案已整合常態守護任務（儲存於 `~/.gemini/config/sidecars/`），支援完全無人值守自轉：
* **`daily-traffic-collector`**（每日清晨 07:00）：
  自動聯網檢索七地熱搜 ➔ 生成 `YYYY-MM-DD.json` ➔ 執行 `sync_traffic_to_gdrive.py` 雲端留痕 ➔ 執行 `build.py` ➔ Git 提交推送 ➔ 留痕至排程儀表板。
* **`weekly-research-sync`**（每週日 20:00）：
  自動從 Google Drive 檢索增量「每週生活熱點」期數 ➔ 匯出 Markdown ➔ 編譯繁簡全歸檔獨立頁 ➔ Git 提交推送。

---

## 🌿 Git 雙分支與發布規範

為確保 GitHub Pages（讀取 `main`）與開發分支保持 100% 同步，每次更新推送需遵守以下標準作業順序：

```bash
# 1. 提交至 main 分支
git checkout main
git add -A
git commit -m "feat(traffic): 自動更新每日流量情報與儀表板"
git push origin main

# 2. Fast-forward 合併回 feature 分支保持乾淨
git checkout feature/frontend-optimization-and-decoupling
git merge main --ff-only
git push origin feature/frontend-optimization-and-decoupling
```

---

## ⚖️ 版權聲明 (Copyright Notice)

版權所有 © 2026 大道至簡 · 簡家旗 (Alex Chiachi Jian)  
保留所有權利。歡迎非商業分享引用，轉載請註明出處與原始連結。詳見 [LICENSE](LICENSE)。

---

大道至簡・簡家旗  
做幸福的事，把幸福做成有價值。
