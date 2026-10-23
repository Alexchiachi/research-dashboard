# 研究報告儀表板

市場調查、流量情報、人物研究、事件追蹤、平台研究——所有研究報告累積在一個頁面，點開即是全文，向下捲動一目瞭然。

- **線上版（繁體）**：https://alexchiachi.github.io/research-dashboard/
- **線上版（簡體）**：https://alexchiachi.github.io/research-dashboard/zh-cn/
- **內容來源**：Google Drive「研究報告庫」（五分類歸檔）
- **核心架構**：報告資料（Markdown）與視覺樣板（Template）解耦，透過 `build.py` 一鍵自動編譯。

---

## 🗂 目錄結構

```text
research-dashboard/
├── reports/                 # 獨立 Markdown 報告存放庫（按五分類歸檔）
│   ├── 01_market/           # 01 市場調查
│   ├── 02_traffic/          # 02 流量情報
│   ├── 03_people/           # 03 人物研究
│   ├── 04_events/           # 04 事件追蹤
│   └── 05_platform/         # 05 平台研究
├── template.html            # 儀表板視覺與互動母樣板（含紙墨美學、防孤字、搜尋與折疊控制）
├── build.py                 # 一鍵編譯腳本（自動計算統計、產出目錄、生成繁簡雙版本）
├── index.html               # 繁體版發布產物（含 hreflang 與「简体」切換鈕）
├── zh-cn/
│   └── index.html           # 簡體版發布產物（含 Noto SC 字型與「繁体」切換鈕）
├── sitemap.xml              # 雙語系 Sitemap
├── robots.txt               # 爬蟲宣告
└── README.md
```

---

## 🚀 如何新增一份研究報告

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
3. 在專案根目錄執行一鍵編譯：
   ```bash
   python3 build.py
   ```
4. 提交並推送至 GitHub：
   ```bash
   git add .
   git commit -m "feat(report): 新增報告"
   git push
   ```

---

大道至簡・簡家旗  
做幸福的事，把幸福做成有價值。
