# 配置文檔

## 概述

配置管理是系統的重要組成部分，負責加載和管理各種配置。該模組依賴於核心模組，並使用 `ConfigUtils` 進行配置管理。

## 目錄結構

```
config/
├── storage.json
├── logging.json
└── security.json
```

## 配置工具

### 配置工具類 (`ConfigUtils`)

配置工具類提供配置加載和保存的功能。

#### 主要方法

- `load_config(config_name)`: 加載指定名稱的配置文件。
- `save_config(config, config_name)`: 保存配置到指定名稱的配置文件。

## 配置文件

### 存儲配置 (`storage.json`)

存儲配置用於設置存儲處理器的參數。

```json
{
  "mode": "local",
  "local": {
    "path": "data",
    "backup_path": "backups"
  },
  "mongodb": {
    "uri": "",
    "database": "",
    "collection": ""
  },
  "notion": {
    "token": "",
    "database_id": "",
    "parent_page_id": ""
  }
}
```

### 日誌配置 (`logging.json`)

日誌配置用於設置日誌記錄的參數。

```json
{
  "level": "INFO",
  "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
  "file": "logs/app.log"
}
```

### 安全配置 (`security.json`)

安全配置用於設置安全相關的參數。

```json
{
  "encryption_key": "",
  "jwt_secret": "",
  "allowed_origins": []
}
```

## 配置加載

配置通過 `ConfigUtils` 加載，例如：

```python
config_utils = ConfigUtils()
storage_config = config_utils.load_config("storage.json")
```

## 配置保存

配置通過 `ConfigUtils` 保存，例如：

```python
config_utils = ConfigUtils()
config_utils.save_config(storage_config, "storage.json")
```

## 配置驗證

配置驗證通過 `ValidationUtils` 執行，確保配置的正確性和完整性。

# 系統配置說明

本文檔詳細說明了爬蟲系統的主要配置文件及其功能。

## 目錄

1. [基本配置](#基本配置)
2. [反檢測配置](#反檢測配置)
3. [驗證碼配置](#驗證碼配置)
4. [數據持久化配置](#數據持久化配置)
5. [字段映射配置](#字段映射配置)
6. [API配置](#api配置)
7. [憑證配置](#憑證配置)

## 基本配置

`config.json` 是系統的主要配置文件，包含以下主要部分：

- 專案資訊：名稱、版本、描述
- 環境設定：時區、編碼、除錯模式
- 模組配置：反檢測、驗證碼、數據持久化
- 爬蟲設定：最大並發任務數、重試設定、模板目錄、預設超時
- 日誌配置：日誌級別、格式、檔案路徑、最大大小、備份數量
- 監控設定：啟用狀態、檢查間隔、指標、警報閾值

## 反檢測配置

`anti_detection_config.json` 包含防止爬蟲被檢測的設定：

- WebDriver配置：無頭模式、視窗大小、位置、超時設定
- 代理設定：代理類型、認證、更換策略
- 用戶代理設定：隨機化、更換策略、真實用戶代理列表
- 請求頭設定：自定義標頭、隨機語言
- 延遲設定：頁面載入、操作間隔、點擊前後

## 驗證碼配置

`captcha_config.json` 定義了驗證碼處理的相關設定：

- 一般設定：最大重試次數、樣本保存、機器學習啟用
- 文字驗證碼：OCR引擎、預處理、置信度閾值
- 滑塊驗證碼：移動策略、軌跡生成、模擬設定
- 點擊驗證碼：檢測方法、延遲設定、置信度閾值

## 數據持久化配置

`persistence_config.json` 管理數據存儲相關設定：

- 本地存儲：啟用狀態、基礎路徑、備份設定
- MongoDB：連接字串、數據庫、集合前綴、批次大小
- Notion：API令牌、數據庫ID、字段映射
- 加密：啟用狀態、密鑰檔案、算法
- 保留策略：最大保留天數、刪除前備份
- 通知：電子郵件、Slack通知設定

## 字段映射配置

`field_mappings.json` 定義了數據字段的映射關係：

- 文章類型：標題、作者、發布日期、內容、URL
- 產品類型：名稱、價格、描述、庫存、分類

## API配置

`api_config.json` 包含外部API的配置：

- OpenAI：REST API設定、認證方式
- Google Cloud：翻譯API設定
- Notion：API版本、數據庫設定
- n8n：自動化平台設定
- make：自動化平台設定
- Webhook：數據處理、通知設定

## 憑證配置

`credentials.json` 存儲各種服務的認證信息：

- MongoDB：連接資訊、認證設定
- SQLite：數據庫設定
- Firebase：專案設定
- AWS：訪問密鑰、區域設定
- Notion：API密鑰、OAuth令牌
- 代理服務：用戶名、密碼、API密鑰
- 驗證碼服務：2captcha、anti-captcha API密鑰
- 加密：密鑰、算法設定
- API：REST、Webhook、n8n、make等服務的認證資訊

## 注意事項

1. 所有包含敏感資訊的配置文件（如 `credentials.json`）應該：
   - 使用環境變數或安全的密鑰管理系統
   - 不要直接提交到版本控制系統
   - 定期更換密鑰和令牌

2. 配置文件的路徑可以通過環境變數 `CONFIG_PATH` 自定義

3. 建議使用配置模板（`_config.json`）作為基礎，然後根據需要覆蓋特定設定

4. 所有時間相關的設定都使用秒為單位，除非特別說明

5. 布爾值設定建議使用明確的 `true` 或 `false`，避免使用 `1` 或 `0` 