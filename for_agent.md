# Steam Scraper 使用指南

这份文档专为 AI Agent 设计，旨在帮助你快速理解、操作并集成 `steam-scraper` 程序。本程序是一个基于 AsyncIO 的高性能 Steam 游戏与评价数据采集工具。

## 1. 程序架构认知

在执行任何操作前，请建立以下认知模型：

*   **核心引擎**: 基于 Python `asyncio` 的异步并发爬虫。
*   **数据流**: Web (Steam Store) -> 内存队列 -> SQLite 数据库 (`data/steam_data.db`) -> Excel/CSV 导出。
*   **状态管理**: 通过 `.checkpoint.json` 记录进度，支持断点续传；通过 `failures.json` 记录失败任务。
*   **交互接口**: CLI (Command Line Interface) 是主要交互方式。

## 2. 环境部署策略

**依赖环境**: Python 3.8+

> [!TIP]
> 如果你不确定具体的指令格式，请一定要随时运行 `python main.py --help` 查看所有可用指令集合。防止出现命令错误。

```bash
# 1. 克隆项目 (假设已在项目根目录，可跳过)
# git clone ... 

# 2. 安装依赖 (必需)
pip install -r requirements.txt

# 3. 验证环境 (可选)
# 运行此命令若无报错且显示 Banner，说明环境正常
python main.py start
```

## 3. 核心作业流程

作为 Agent，你应该根据任务目标选择合适的工作流。

### 场景 A: 首次全量采集 (常用)

目标：从零开始抓取所有游戏及其评价，并导出数据。

1.  **启动全流程任务**:
    ```bash
    python main.py all
    ```
    *   *行为*: 依次执行 `games` (抓取游戏信息) -> `reviews` (抓取评价) -> `export` (导出文件)。
    *   *耗时*: 取决于游戏数量和网络，可能需要数小时。

2.  **应对中断**:
    如果任务因意外停止（网络断开、系统重启），**不要**重新运行 `python main.py all`（这会清除进度！），请务必使用：
    ```bash
    python main.py all --resume
    ```

### 场景 B: 分步执行

目标：需要对每个阶段进行单独控制或调试。

1.  **阶段一：采集游戏基本信息**
    ```bash
    python main.py games
    # 调试建议：仅抓取前 5 页进行测试，但是请先询问用户究竟准备爬取几页
    # python main.py games --pages 5
    ```

2.  **阶段二：采集评价历史**
    ```bash
    python main.py reviews
    # 前置条件：数据库中必须已有游戏数据
    ```

3.  **阶段三：数据导出**
    ```bash
    # 导出 Excel (默认)
    python main.py export
    
    # 导出 CSV (推荐大数据量使用，也可以一并完成做掉)
    python main.py export --format csv
    ```

### 场景 C: 故障修复

目标：处理网络波动导致的抓取失败。

1.  **检查失败**: 程序运行结束后提醒有失败项目。
2.  **执行重试**:
    ```bash
    python main.py retry
    ```
    *   *策略*: 该命令会自动读取 `failures.json` 和断点记录，针对性地重试失败的 ID。建议多次运行直到失败列表清空。

## 4. 配置优化策略 (`config.yaml`)

你可以通过修改 `config.yaml` 来调整程序行为。

| 参数路径 | 默认值 | Agent 调整策略 |
| :--- | :--- | :--- |
| `scraper.max_workers` | `20` | **谨慎调整**。增加可提升速度，但超过 `50` 极易触发 Steam 的 IP 封禁 (HTTP 429)。若遇到大量连接错误，请降至 `10`。 |
| `scraper.language` | `english` | 若需中文数据，修改为 `schinese`。 |
| `scraper.currency` | `us` | 若需人民币价格，修改为 `cn`。 |
| `http.timeout` | `30` | 网络环境较差时可适当增加至 `60`。 |
| `http.max_retries` | `3` | 建议保持默认，依靠外部的 `retry` 命令处理顽固失败。 |

## 5. 数据交互指南

AI 可以直接读取生成的数据文件进行分析，无需经过 API。

### 数据库模式 (SQLite: `data/steam_data.db`)

可以直接使用 SQL 语句查询：

*   **表 `games`**:
    *   `app_id` (PK): 游戏 ID
    *   `name`: 游戏名称
    *   `price`: 价格字符串
    *   `developers`: JSON 数组字符串 (e.g., `["Valve", "Hidden Path"]`)
    *   `publishers`: JSON 数组字符串
    *   `genres`: JSON 数组字符串
    *   `description`: 游戏描述

*   **表 `reviews`**:
    *   `app_id` (FK): 对应 games 表
    *   `date`: 日期 (YYYY-MM-DD)
    *   `recommendations_up`: 好评数（累计）
    *   `recommendations_down`: 差评数（累计）
    *   *注意*: 联合主键 (`app_id`, `date`)

### 导出文件

*   **Excel (`data/steam_data.xlsx`)**: 适合人类阅读，包含 `Games` 和 `Reviews` 两个 Sheet。
*   **CSV (`data/steam_games.csv`, `data/steam_reviews.csv`)**: 适合程序后续处理（如 Pandas 加载），编码为 `utf-8-sig`。

## 6. Agent 操作注意事项 (Do's and Don'ts)

*   **DO** 优先使用 `--resume` 参数，除非你或用户明确想要丢弃所有既往进度。
*   **DO** 在长时间任务后运行 `python main.py retry` 确保数据完整性。
*   **DO** 监控 `data/` 目录的文件变化来确认程序是否在工作。
*   **DON'T** 在程序运行时手动删除 `.checkpoint.json`，这会导致进度丢失。
*   **DON'T** 频繁使用 `python main.py reset`，这会物理删除所有数据文件且不可恢复。

## 7. 常见报错

*   **Error**: `Database is locked`
    *   *原因*: 可能有其他进程（或你打开了 SQLite 浏览器）占用了数据库文件。
    *   *解决*: 关闭所有访问该 DB 的程序，等待几秒后重试。

*   **Error**: `429 Too Many Requests`
    *   *原因*: 并发过高。
    *   *解决*: 修改 `config.yaml` 降低 `max_workers`，等待一段时间后使用 `retry` 命令。

*   **Warning**: `检测到 X 个游戏爬取失败记录...`
    *   *策略*: 在运行 `reviews` 之前，最好先运行 `retry --type game` 修复游戏数据，否则评价数据可能失去关联对象。
