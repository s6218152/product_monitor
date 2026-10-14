# facebook-product-monitor

以 JSON fixture 驗證核心流程，並提供 Playwright Marketplace 與 Facebook Groups collector。

## 功能

- Marketplace listing 與 Group post 統一成 `ProductListing`
- SQLite 儲存，以 `(source, source_id)` 去重；`last_seen_at` 保存來源貼文時間，`observed_at` 另存最近抓取時間
- 保存最新觀測與是否符合通知條件，商品漲價或變更地區後不會沿用舊資料通知
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

在 `.env` 以逗號分隔設定 `FACEBOOK_GROUP_URLS` 後抓取群組貼文：

```bash
python main.py groups --live
```

產生可直接貼到 Telegram 的 HTML 格式（時間自動轉成台灣時間）：

```bash
python main.py telegram --limit 10
```

在 `.env` 設定 `TELEGRAM_BOT_TOKEN` 與 `TELEGRAM_CHAT_ID` 後直接發送：

```bash
python main.py telegram --limit 10 --send
```

`--send` 只會傳送符合條件且尚未通知，或低於上次通知價格的商品；每筆成功送達後才標記，失敗的商品會保留供下次重試。

曾通知商品降價後也會再次通知，標記使用實際送出的價格。單筆失敗會記錄原因並延後至少 5 分鐘重試，
其餘商品仍繼續發送；整批有失敗時指令回傳非零結束碼。帳號或聊天室權限錯誤會停止整批，
限流時依 [Telegram Bot API 的 `retry_after`](https://core.telegram.org/bots/api#responseparameters) 延後重試。
HTML 長訊息會在保留格式與跳脫字元的情況下分段。
`--limit` 必須大於 0，通知資格與數量限制在 SQLite 查詢中處理。

登入狀態儲存在 `.facebook-profile/`，已被 Git 忽略。它含敏感 session 資料，不可分享或提交。請勿將 `FACEBOOK_PROFILE_DIR` 指向日常使用的 Chrome profile。Facebook 頁面結構可能改變；collector 只依賴 Marketplace 商品連結，解析失敗時可先提高 `LOG_LEVEL` 檢查。

可用 `--database /path/to/file.db` 暫時覆寫 `.env` 中的 `DATABASE_PATH`。

程式目前不會設定 Facebook 搜尋地區與半徑；請在 Marketplace 頁面調整搜尋範圍。
舊版 `MARKETPLACE_LOCATION`、`MARKETPLACE_RADIUS_KM` 沒有實際作用，已移除。
商品通知的面交地區由 `app/products/targets.py` 的 `TARGET_LOCATIONS` 篩選。
首次開啟舊資料庫時會自動新增並回填通知資格、容量與最近觀測等欄位。

## 架構

- `app/collectors/`：來源介面、原始模型、fixture 與 Playwright adapter
- `app/products/`：可獨立測試的匹配、解析與正規化邏輯
- `app/database/`：統一資料模型、SQLite schema 與 repository
- `app/monitors/`：協調 collector、matcher、normalizer 與 repository
- `app/notifications/`：輸出 adapter
- `tests/fixtures/`：不含帳號、cookie 或 session 的範例資料

真實 Facebook 實作應只放在 collector layer，business logic 不依賴 DOM、Playwright 或 Facebook GraphQL 格式。

## 排程與維護

VM 使用 `scripts/run-monitor.sh`，Groups 或 Marketplace 失敗時仍執行另一來源及 Telegram。
腳本自動定位專案路徑，使用 `.venv/bin/python`，不再依賴寫死的 VM 路徑或系統 `timeout` 指令。
每個來源逾時 420 秒、Telegram 90 秒，逾時時終止整個子程序群組。
監控與維護內建共用 `/tmp/facebook-product-monitor.lock`；可用 `.env` 或環境變數 `MONITOR_LOCK_PATH` 覆寫。
鎖被占用時跳過本輪；相同鎖路徑、未使用 `--close` 的既有外層 `flock` 排程也可沿用。
排程腳本支援 Linux/macOS；手動執行單一 CLI 指令不會取得排程鎖，請避免與維護同時操作專用 profile。
建議每 10 分鐘執行，日誌包含來源結束碼、篩選淘汰原因、群組耗時與完整流程秒數。

每月以 `.venv/bin/python scripts/maintenance.py` 執行維護：刪除超過 90 天未再觀測，且已通知完畢或不符合條件的商品；
符合條件且尚未通知或正在等待降價通知的商品會保留。維護也會壓縮 SQLite，
並清除專用 profile 的 Cache、Code Cache、GPUCache（保留登入資料）。
維護會自行取得相同鎖，不需另外加鎖。
未知貼文時間仍可通知並顯示「未知」，不會以抓取時間冒充作者時間。
已通知商品低於上次通知價格時會再次通知。多容量貼文保守排除，避免價格與容量配對錯誤。
多型號或多售價貼文也保守排除，避免把其他手機的價格套到目標商品。
Groups 請求時間排序，但 Facebook 不一定採用；log 會記錄排序未確認、無權限與解析結果。

## 快速增量監控（取代舊 Cron）

新版常駐入口：`.venv/bin/python scripts/fast_monitor.py`。
Marketplace 預設每 120 秒掃描一次，10 個群組分別每 300 秒輪巡；這些是目標間隔，
實際延遲受 Facebook 載入、商品數量與 Telegram 影響，超過預定掃描時間會記錄 `scan_overdue`。
共用一個登入 browser context、三個頁面，避免兩個 Chromium 同時使用同一個 profile。
單一商品詳情使用 12 秒 navigation timeout，並分開排入處理佇列；先處理新商品，
不因每輪重讀全部舊商品而拖延。詳情缺少來源資料時不冒用搜尋卡時間或描述，稍後重試。
商品符合條件就立即入庫與傳送，失敗保留重試；即使群組失敗仍繼續其他工作。
每 15 分鐘背景補抓並逐次擴大到最多 18 次捲動，同時刷新已見商品以檢查降價。

Marketplace 請求最新排序，但只有頁面控件顯示對應排序時記錄確認；
未確認則記錄 `marketplace_sort_unconfirmed`。群組採「最新」请求，若抓取為零，
下次輪巡改用一般頁面，並明確標示排序未確認。連續三次群組為零、掃描失敗或嚴重落後，
會傳送 Telegram 異常告警，同一異常最多每 30 分鐘一則。
通知 log 包含上架到發送、首次發現到發送兩種延遲及 `within_10min`；上架時間未知時為 unknown。
Facebook 搜尋尚未顯示的商品、待審核貼文、限流與登入失效無法保證 10 分鐘內通知。
建議驗收 7 天並以人工抽樣檢查漏抓，不能只统计已發送商品。

可在 `.env` 設定 `FAST_MARKETPLACE_INTERVAL_SECONDS=120` 和 `FAST_GROUP_INTERVAL_SECONDS=300`。
瀏覽器每 4 小時回收重建；systemd 管理整個程序群組，停止時同時結束 Chromium 子程序。

### VM 安裝方式

部署前請先備份並移除舊 crontab 中帶有 `# facebook-product-monitor` 的監控、維護兩行，
保留其他排程。新版常駐程序持有同一把鎖，舊 Cron 與手動 runner 會被鎖阻擋，不能一起使用。
以下 unit 的帳號和路徑預設為本專案目前 VM，其他環境須調整。

```bash
sudo install -m 644 deploy/facebook-product-monitor.service /etc/systemd/system/
sudo install -m 644 deploy/facebook-product-monitor-maintenance.service /etc/systemd/system/
sudo install -m 644 deploy/facebook-product-monitor-maintenance.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now facebook-product-monitor.service
sudo systemctl enable --now facebook-product-monitor-maintenance.timer
systemctl status facebook-product-monitor.service
journalctl -t facebook-product-monitor -f
```

每月維護 timer 會先停止常駐程序，再清理資料與快取，最後重啟监控；避免快取清理與瀏覽器使用重疊。
回復舊方式：停止並停用新版 service/timer，再還原備份 crontab。
本版只提供程式與部署設定，GitHub 更新不會自動切換 VM 的舊排程。

若無 sudo 權限，可以由 Cron 每分鐘與開機執行 `scripts/fast_supervisor.py run`。
它取得共用鎖後啟動常駐監控，已在執行時會安靜略過，程序中止後下一分鐘恢復。
每月維護改執行 `scripts/fast_supervisor.py maintain`，暫停啟動、驗證 PID 與使用者後正常停止監控，
取得鎖才清理，完成後取消暫停；下一分鐘恢復。
這是 systemd 的替代方案，兩者請擇一使用。PID/暫停狀態保存在被 Git 忽略的 `data/`。

頁面 crash/close 或 `TargetClosedError` 會重建對應頁面；無法建立新頁面時立即重建瀏覽器，
保留待處理佇列，不等四小時週期。連續兩次載入逾時也會回收該頁面並安排短間隔重試。
詳情讀取失敗保留商品 ID 與首次發現時間，依 30/60/120/240/300 秒退避重試，
重試中的商品不阻擋新商品，日誌記錄 `detail_retry_scheduled` 和 `page_recovered`。
單次逾時記錄日誌，連續三次失敗才告警；`scan_completed` 的 outcome 明確區分成功與失敗。
