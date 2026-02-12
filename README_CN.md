<div align="center">
  <p align="center">
    <img src="assets/demo.svg" alt="Terminal Demo" width="600">
  </p>

  <h1>Steam Scraper</h1>
  <p>
    <strong>小白都能上手的简单、高效、可视化的 Steam 评论数据爬虫。</strong>
  </p>
  <p>
    专为数据分析与挖掘设计。基于 AsyncIO 全异步架构，令数据抓取自然流畅。
  </p>

  <p>
    <a href="LICENSE"><img src="https://img.shields.io/github/license/SeraphinaGlacia/steam-scraper?style=flat-square" alt="License"></a>
    <img src="https://img.shields.io/badge/python-3.8+-blue?style=flat-square&logo=python&logoColor=white" alt="Python Version">
    <img src="https://img.shields.io/github/repo-size/SeraphinaGlacia/steam-scraper?style=flat-square" alt="Repo Size">
    <img src="https://img.shields.io/badge/arch-AsyncIO-green?style=flat-square" alt="Architecture">
  </p>

  <p>
    <a href="README.md">English</a> • 
    <a href="README_CN.md">中文</a>
    <br>
  </p>
</div>

---

> [!TIPS] 使用 AI 工具辅助
> 本项目包含了专为 Agent 设计的 [for_agent.md](for_agent.md) 指南。如果你是技术小白，可以尝试使用 AI 工具来辅助操作本程序。
> 
> 如果你正在使用 **Cursor**、**Google Antigravity** 或其他拥有 Agent 能力的 AI 辅助 IDE 或 CLI 工具，只需将该文件**添加至上下文**。AI 即可立刻学会本程序的使用策略与纠错机制，从而能够辅助你操作本程序。


## ✨ 为什么选择它？

- **⚡️ 极速采集体验**
    - 基于 **AsyncIO** 重构的核心引擎，单机即可轻松跑满网络带宽。
    - 智能并发控制 + 毫秒级请求间隔，在速度与反爬封锁之间找到完美平衡点。

- **📺 美观易懂的终端界面**
    - 看不懂代码？没有关系！本程序不止有冰冷的代码，更有美观易懂的终端界面。
    - 集成 **Rich** 库构建，提供清晰的控制指令、进度条与统计面板。即使是**技术小白**，也能通过直观的仪表盘操作并掌握运行状态。

- **🛡️ 告别“从头再来”**
    - 爬到 99% 突然断网或报错？别担心。
    - 内置工业级 **断点续传** 机制，随时中断，随时继续。每一条已抓取的数据都会被安全保存。

- **🚀 分析即刻开始**
    - 不仅仅是抓取，更是为了分析。
    - 数据直接存入 **SQLite**，结构严谨；支持一键导出 **Excel** 报表，无需编写额外代码即可开始数据分析。

- **🔧 零代码配置**
    - 并发数、超时时间、目标货币区... 所有参数均可通过 `config.yaml` 调整。
    - 即使是不懂代码的用户，也能通过简单的配置定制自己的爬虫。

---

## 🛠️ 快速开始

### 1. 安装依赖

确保你的 Python 版本 >= 3.8。

```bash
git clone https://github.com/SeraphinaGlacia/steam-scraper.git
cd steam-scraper
pip install -r requirements.txt
```

### 2. 体验炫酷启动页 (彩蛋🎪) 

我们在命令行帮助中隐藏了这个命令，虽然其没有实际作用，但你可以直接运行它来测试环境配置，并欣赏启动画面：

```bash
python main.py start
```

### 3. 标准工作流

最常用的全自动一条龙服务：

```bash
# 1. 启动完整抓取任务（游戏信息 -> 评价历史 -> 导出 Excel + CSV）
python main.py all

# 2. 如果任务中断，恢复进度
python main.py all --resume
```

---

## 📖 详细命令指南

我们的 CLI 设计遵循 UNIX 哲学，提供丰富的子命令：

### 🎮 抓取游戏信息 (`games`)

仅抓取 Steam 商店的游戏基础数据（价格、开发商、好评率等）。

```bash
python main.py games              # 抓取所有分页
python main.py games --pages 10   # 仅抓取前 10 页（适合测试）
python main.py games --resume     # 从上次中断处继续
```

### 📝 抓取评价历史 (`reviews`)

针对基础信息已写入数据库的游戏，抓取其历史评价趋势数据。

```bash
python main.py reviews            # 抓取数据库中所有游戏的评价
python main.py reviews --resume   # 断点续传
```

### 📤 导出数据 (`export`)

将 SQLite 数据库中的内容导出为 Excel 文件。

```bash
python main.py export
# 输出文件默认位于 data/steam_data.xlsx

# 如果数据量巨大（超过 Excel 104万行限制），可以导出为 CSV：
python main.py export --format csv
# 将在 data/ 目录下生成 steam_games.csv 和 steam_reviews.csv
```

### 🔄 失败重试 (`retry`)

程序会自动记录所有失败的请求。由于网络波动导致的失败，可以通过此命令一键修复。

```bash
python main.py retry              # 重试所有失败任务
python main.py retry --type game  # 仅重试游戏信息任务
```

### 🧹 维护与清理 (`clean` / `reset`)

保持项目整洁。

> [!CAUTION]
> `reset` 命令会删除所有数据，包括数据库、导出文件、失败日志等，且不可恢复！

```bash
python main.py clean    # 清理 Python 缓存、断点文件等临时文件
python main.py reset    # ⚠️【高危】删除数据库和所有数据，重置为初始状态
```

---

## ⚙️ 配置说明

所有魔法都在 `config.yaml` 中定义，你可以随心定制：

```yaml
scraper:
  language: english       # Steam 商店语言
  currency: us            # 货币代码
  category: "998"         # 分类 ID（998 为游戏）
  max_workers: 20         # 并发数（AsyncIO 模式下建议 15-20，过高可能导致 IP 封禁）

http:
  timeout: 30             # 请求超时（秒）
  max_retries: 3          # 最大重试次数
  min_delay: 0.5          # 请求间隔最小值（秒）
  max_delay: 1.5          # 请求间隔最大值（秒）

output:
  data_dir: ./data        # 数据输出目录
  checkpoint_file: .checkpoint.json  # 断点文件
```

---

## 📂 数据结构

运行后，`data/` 目录将包含：

| 文件 | 描述 |
| :--- | :--- |
| `steam_data.db` | **核心数据库** (SQLite)。包含 `games` 和 `reviews` 两张表，适合开发者直接查询。 |
| `steam_data.xlsx` | **最终报表**。包含两个 Sheet，无需写代码即可分析数据。 |
| `steam_*.csv` | **CSV 数据集**。当数据量超过 Excel 限制时生成，采用 UTF-8-SIG 编码，兼容 Excel。 |
| `failures.json` | **失败日志**。记录失败的 ID、原因、时间戳等详细信息，便于排查问题。`retry` 成功后会删除对应条目。 |
| `.checkpoint.json` | **进度存档**。记录已完成/失败的 ID 列表，用于 `--resume` 断点续传。包含 games 和 reviews 的独立状态。 |

---

<div align="center">
  <p>Made with ❤️ by SeraphinaGlacia / Zhou Xinlei</p>
</div>
