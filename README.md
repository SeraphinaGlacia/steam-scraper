<div align="center">
  <h1>Simple Steam Scraper</h1>
  <p>
    一个基于 Python 的轻量级、模块化且支持断点续传的 Steam 游戏数据爬虫。<br>
    旨在帮助数据分析爱好者或科研人员快速获取 Steam 商店的游戏基础信息及历史评价趋势。
  </p>

  <p>
    <a href="LICENSE"><img src="https://img.shields.io/github/license/SeraphinaGlacia/simple-steam-scraper?style=flat-square" alt="License"></a>
    <img src="https://img.shields.io/badge/python-3.8+-blue?style=flat-square&logo=python&logoColor=white" alt="Python Version">
    <img src="https://img.shields.io/github/repo-size/SeraphinaGlacia/simple-steam-scraper?style=flat-square" alt="Repo Size">
  </p>

  <p>
    <a href="README.md">中文</a> • 
    <a href="README_EN.md">English</a>
  </p>
</div>

---

## ✨ 功能特性

- 🎮 **爬取 Steam 商店游戏基础信息**（名称、价格、开发商、类型等）
- 📊 **爬取游戏评价历史数据**（好评/差评数量按日期统计）
- ⚡️ **高并发采集**，速度提升 10+ 倍
- 🗄️ **SQLite 数据存储**，高效、稳定、无碎片
- 💾 **一键导出 Excel**，包含游戏信息和评价数据
- ⏸️ **支持断点续爬**，意外中断也不怕
- 🔄 **支持失败自动记录与重试**，保证数据完整性
- ⚙️ **可配置的请求参数**，灵活适应不同网络环境

## 🚀 快速开始

### 0. 获取项目代码

1.  **打开命令行工具**：
    *   **Windows**: 按 `Win + R`，输入 `cmd` 并回车。
    *   **Mac**: 打开 `Terminal` (终端)。

2.  **克隆仓库**：
    在终端中输入以下命令并执行，将代码下载到本地：
    ```bash
    git clone https://github.com/SeraphinaGlacia/simple-steam-scraper.git
    ```

3.  **进入项目目录**：
    ```bash
    cd simple-steam-scraper
    ```

### 1. 📦 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 📖 查看帮助

```bash
python main.py --help
```

### 3. 🕸️ 爬取全部游戏（推荐-完整流程）

```bash
# 爬取全部游戏信息 + 评价历史（自动获取总页数）
python main.py all

# 如果中途中断，可从断点继续
python main.py all --resume
```

### 4. 🪜 分步骤运行（进阶用法）

```bash
# 第一步：爬取游戏基础信息
python main.py games              # 爬取全部页面
python main.py games --pages 100  # 只爬取前 100 页

# 第二步：爬取评价历史（基于上一步生成的 app_id 列表）
python main.py reviews
```

### 5. 🧹 清理缓存和临时文件

```bash
python main.py clean
```

### 6. 🔄 失败重试

如果爬取过程中出现网络错误等问题，程序会自动记录失败项目。可以使用以下命令进行重试：

```bash
# 重试所有失败项目（游戏信息 + 评价）
python main.py retry

# 仅重试失败的游戏基础信息
python main.py retry --type game

# 仅重试失败的评价历史
python main.py retry --type review
```

### 7. 🗑️ 重置项目

> [!CAUTION]
> 警告：此操作不可恢复!

如果需要清空所有已抓取的数据（数据库、Excel）和缓存文件，重新开始：

```bash
python main.py reset
```

程序会要求两次确认以防止误操作。

### 8. 📤 导出数据

将数据库中的数据导出到 Excel 文件（包含两个 Sheet）：

```bash
python main.py export
```

### 9. 📂 输出文件

所有数据文件保存在 `data/` 目录：

| 文件 | 说明 |
|------|------|
| `data/steam_data.db` | SQLite 数据库文件（核心数据） |
| `data/steam_data.xlsx` | 导出的 Excel 数据表（包含 Games 和 Reviews） |

## 🏗️ 项目结构

```
simple_steam_scraper/
├── src/                          # 核心模块
│   ├── config.py                 # 配置管理
│   ├── models.py                 # 数据模型
│   ├── scrapers/                 # 爬虫模块
│   │   ├── game_scraper.py       # 游戏信息爬虫
│   │   └── review_scraper.py     # 评价历史爬虫
│   ├── database.py               # 数据库管理
│   └── utils/                    # 工具模块
│       ├── http_client.py        # HTTP 客户端
│       ├── checkpoint.py         # 断点续爬
│       └── failure_manager.py    # 失败记录管理
├── data/                         # 数据输出目录
├── config.yaml                   # 配置文件
├── main.py                       # 统一入口
├── README.md                     # 中文文档
└── README_EN.md                  # 英文文档
```

## ⚙️ 配置说明

编辑 `config.yaml` 自定义爬虫行为：

```yaml
scraper:
  language: english    # Steam 商店语言
  currency: us         # 货币代码
  category: "998"      # 分类 ID（998 为游戏）
  max_workers: 10      # 并发线程数（默认为 10，过高可能导致 IP 封禁）

http:
  timeout: 30          # 请求超时（秒）
  max_retries: 3       # 最大重试次数
  min_delay: 1.0       # 请求间隔最小值（秒）
  max_delay: 3.0       # 请求间隔最大值（秒）

output:
  data_dir: ./data     # 数据输出目录
  checkpoint_file: .checkpoint.json  # 断点文件
```

## 🧩 附录：运行机制

1.  **并发采集与入库**
    - 程序使用多线程技术（`ThreadPoolExecutor`）并发访问 Steam 搜索页面和 API 接口。
    - **游戏信息**：采集到的游戏基础信息（id, name, price 等）实时存入 SQLite 数据库 `games` 表中。
    - **评价历史**：针对每个游戏，并发采集其评价历史数据，并存入数据库 `reviews` 表中。
    - **断点续传**：利用数据库的主键约束和 `checkpoint` 机制，智能跳过已采集的项目。

2.  **数据导出**
    - 采集完成后，使用 `export` 命令从数据库中读取所有数据。
    - **输出文件**：生成一个包含 `Games` 和 `Reviews` 两个 Sheet 的 Excel 文件 (`data/steam_data.xlsx`)，便于后续分析。



---

<div align="center">
  <p>MIT License © 2025</p>
</div>
