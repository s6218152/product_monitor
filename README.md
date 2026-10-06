# facebook-product-monitor

以 JSON fixture 驗證核心流程，並提供可選的 Playwright Marketplace collector。Groups 目前仍使用 fixture。

## 功能

- iPhone 17 Pro Max 關鍵字比對與排除求購、配件及其他型號貼文
- Marketplace 只保留新竹市、新竹縣、桃園市、桃園縣、苗栗市或苗栗縣商品
- 價格條件：512G 不超過 NT$37,000；256G 不超過 NT$32,000
- iPhone 型號、容量、價格、顏色、電池健康度、地區與交易方式解析
- Marketplace listing 與 Group post 統一成 `ProductListing`
- SQLite 儲存，以 `(source, source_id)` 去重；`last_seen_at` 保存來源貼文時間
- fixture collector 與 CLI

## 安裝與測試

需要 Python 3.11 以上版本。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env
pytest
```

## 執行

```bash
python main.py marketplace --fixture tests/fixtures/marketplace_iphone17_pro_max.json
python main.py groups --fixture tests/fixtures/group_iphone.json
```

## 實際監控 Marketplace

安裝 Playwright 與專用 Chromium：

```bash
python -m pip install -e '.[dev,facebook]'
playwright install chromium
```

第一次使用時，開啟專用瀏覽器 profile 並手動登入 Facebook：

```bash
python main.py marketplace-login
```

登入完成後執行：

```bash
python main.py marketplace --live
```

產生可直接貼到 Telegram 的 HTML 格式（時間自動轉成台灣時間）：

```bash
python main.py telegram --limit 10
```

在 `.env` 設定 `TELEGRAM_BOT_TOKEN` 與 `TELEGRAM_CHAT_ID` 後直接發送：

```bash
python main.py telegram --limit 10 --send
```

`--send` 只會傳送 `notified_at` 尚未設定的商品；每筆成功送達後才標記，失敗的商品會保留供下次重試。

登入狀態儲存在 `.facebook-profile/`，已被 Git 忽略。它含敏感 session 資料，不可分享或提交。請勿將 `FACEBOOK_PROFILE_DIR` 指向日常使用的 Chrome profile。Facebook 頁面結構可能改變；collector 只依賴 Marketplace 商品連結，解析失敗時可先提高 `LOG_LEVEL` 檢查。

可用 `--database /path/to/file.db` 暫時覆寫 `.env` 中的 `DATABASE_PATH`。

## 架構

- `app/collectors/`：來源介面、原始模型、fixture 與 Playwright adapter
- `app/products/`：可獨立測試的匹配、解析與正規化邏輯
- `app/database/`：統一資料模型、SQLite schema 與 repository
- `app/monitors/`：協調 collector、matcher、normalizer 與 repository
- `app/notifications/`：輸出 adapter
- `tests/fixtures/`：不含帳號、cookie 或 session 的範例資料

真實 Facebook 實作應只放在 collector layer，business logic 不依賴 DOM、Playwright 或 Facebook GraphQL 格式。
