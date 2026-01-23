# Simple Steam Scraper

一个基于 Python 的轻量级、模块化且支持断点续传的 Steam 游戏数据爬虫，旨在帮助数据分析爱好者或科研人员快速获取 Steam 商店的游戏基础信息及历史评价趋势，数据直接导出为 .xlsx 格式，便于后续进行可视化分析或商业洞察。

## 功能特性

- 🎮 爬取 Steam 商店游戏基础信息（名称、价格、开发商、类型等）
- 📊 爬取游戏评价历史数据（好评/差评数量按日期统计）
- 💾 导出为 .xlsx 文件
- ⏸️ 支持断点续爬
- 🔄 支持失败自动记录与重试
- ⚙️ 可配置的请求参数

## 快速开始

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

### 1. 安装依赖

```bash
pip install requests beautifulsoup4 pandas openpyxl pyyaml
```

### 2. 查看帮助

```bash
python main.py --help
```

### 3. 爬取全部游戏（推荐-完整流程）

```bash
# 爬取全部游戏信息 + 评价历史（自动获取总页数）
python main.py all

# 如果中途中断，可从断点继续
python main.py all --resume
```

### 4. 分步骤运行（进阶用法）

```bash
# 第一步：爬取游戏基础信息
python main.py games              # 爬取全部页面
python main.py games --pages 100  # 只爬取前 100 页

# 第二步：爬取评价历史（基于上一步生成的 app_id 列表）
python main.py reviews
```

### 5. 清理缓存和临时文件

```bash
python main.py clean
```

### 6. 失败重试

如果爬取过程中出现网络错误等问题，程序会自动记录失败项目。可以使用以下命令进行重试：

```bash
# 重试所有失败项目（游戏信息 + 评价）
python main.py retry

# 仅重试失败的游戏基础信息
python main.py retry --type game

# 仅重试失败的评价历史
python main.py retry --type review
```

### 7. 输出文件

所有数据文件保存在 `data/` 目录：

| 文件 | 说明 |
|------|------|
| `steam_games_{当前时间戳}.xlsx` | 游戏基础信息 |
| `steam_appids.txt` | 游戏 ID 列表 |
| `steam_recommendations_data/` | 每个游戏的评价历史 |

## 项目结构

```
simple_steam_scraper/
├── src/                          # 核心模块
│   ├── config.py                 # 配置管理
│   ├── models.py                 # 数据模型
│   ├── scrapers/                 # 爬虫模块
│   │   ├── game_scraper.py       # 游戏信息爬虫
│   │   └── review_scraper.py     # 评价历史爬虫
│   ├── exporters/                # 导出模块
│   │   └── excel.py              # Excel 导出
│   └── utils/                    # 工具模块
│       ├── http_client.py        # HTTP 客户端
│       ├── checkpoint.py         # 断点续爬
│       └── failure_manager.py    # 失败记录管理
├── data/                         # 数据输出目录
├── config.yaml                   # 配置文件
├── main.py                       # 统一入口
└── README.md
```

## 配置说明

编辑 `config.yaml` 自定义爬虫行为：

```yaml
scraper:
  language: english    # Steam 商店语言
  currency: us         # 货币代码
  category: "998"      # 分类 ID（998 为游戏）

http:
  timeout: 30          # 请求超时（秒）
  max_retries: 3       # 最大重试次数
  min_delay: 1.0       # 请求间隔最小值（秒）
  max_delay: 3.0       # 请求间隔最大值（秒）

output:
  data_dir: ./data     # 数据输出目录
```

## 附录：运行机制

本程序通过模拟用户浏览与数据接口查询的方式，实现对 Steam 游戏数据的自动化采集与整合。核心流程与文件交互如下：

1.  **遍历并生成 App ID 清单**

  - 程序首先访问 Steam 搜索页面，遍历指定分类下的游戏列表，解析 HTML 结构提取基础元数据（App ID）。
  - **输出文件**：提取到的 ID 会被实时写入 `data/steam_appids.txt`，作为后续步骤的索引清单。

2.  **进一步获取游戏详情信息**

  - 程序读取上一步生成的清单（或直接利用内存中的数据），调用 Steam Store API 接口批量获取游戏详细信息（id, name, release_date, price, developers 等）。
  - **输出文件**：所有基础信息会被结构化并保存为 `data/steam_games_{当前时间戳}.xlsx`，这是游戏基础信息数据总表。

3.  **获取游戏评价历史**

  - 针对清单中的每一个 App ID，程序进一步请求 Steam 评价直方图接口，获取自发布以来的评价趋势数据。
  - **输出文件**：每个游戏的评价历史数据会被保存至 `data/steam_recommendations_data/` 目录下，文件夹内会包含多个 .xlsx 文件，命名格式为 `steam_recommendations_{AppID}.xlsx`，每个文件记录了对应游戏在不同时间跨度的好评/差评数据。

4.  **完成**

  - 最终，程序确保所有采集到的信息（基础详情数据 + 评价历史数据）都被完整保存，便于后续分析工具直接读取。

## License

MIT License
