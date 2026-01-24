<div align="center">
  <p align="center">
    <img src="assets/demo.svg" alt="Terminal Demo" width="600">
  </p>

  <h1>Simple Steam Scraper</h1>
  <p>
    <strong>一个基于 Python 的高性能 Steam 数据爬虫，为您带来极致的数据爬取体验。</strong>
  </p>
  <p>
    不仅功能强大，更优雅迷人。基于 <code>Rich</code> 构建的沉浸式 TUI，让数据采集不再枯燥。
  </p>

  <p>
    <a href="LICENSE"><img src="https://img.shields.io/github/license/SeraphinaGlacia/simple-steam-scraper?style=flat-square" alt="License"></a>
    <img src="https://img.shields.io/badge/python-3.8+-blue?style=flat-square&logo=python&logoColor=white" alt="Python Version">
    <img src="https://img.shields.io/github/repo-size/SeraphinaGlacia/simple-steam-scraper?style=flat-square" alt="Repo Size">
    <img src="https://img.shields.io/badge/UI-Rich-purple?style=flat-square" alt="UI powered by Rich">
  </p>

  <p>
    <a href="README.md">中文</a> • 
    <a href="README_EN.md">English</a>
    <br>
  </p>
</div>

---

## ✨ 核心特性

- **🎨 极致的终端 UI 体验**
    - 告别滚动的纯文本日志，拥抱 **Panel**、**Table** 和 **Progress**。
    - 关键信息高亮显示，错误日志清晰可读，让爬虫运行状态一目了然。
    - 更有炫酷的 ASCII Art 启动页，仪式感拉满。

- **🚀 高性能并发采集**
    - 内置 `ThreadPoolExecutor` 线程池，支持 **10+ 倍** 速度的高并发抓取。
    - 智能限流与重试机制，在速度与稳定性之间找到完美平衡。

- **🛡️ 健壮的断点续传**
    - 意外断电？网络中断？不必担心！
    - 实时保存进度，随时通过 `--resume` 命令无缝接续，拒绝重复劳动。

- **🗄️ 企业级数据管理**
    - **SQLite 存储**：并非简单的 CSV，而是使用关系型数据库，结构严谨，查询高效。
    - **一键导出**：支持将所有数据（游戏基础信息 + 历史评价）导出为格式完美的 **Excel** 报表。

- **🔄 智能失败重试**
    - 自动捕获所有失败的任务 ID 与原因。
    - 提供交互式的重试命令 `retry`，精准打击失败项，确保数据 100% 完整。

---

## 🛠️ 快速开始

### 1. 安装依赖

确保你的 Python 版本 >= 3.8。

```bash
git clone https://github.com/SeraphinaGlacia/simple-steam-scraper.git
cd simple-steam-scraper
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
# 1. 启动完整抓取任务（游戏信息 -> 评价历史 -> 导出 Excel）
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
  max_workers: 10         # 并发线程数（默认为 10，过高可能导致 IP 封禁）

http:
  timeout: 30             # 请求超时（秒）
  max_retries: 3          # 最大重试次数
  min_delay: 1.0          # 请求间隔最小值（秒）
  max_delay: 3.0          # 请求间隔最大值（秒）

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
| `failures.json` | **失败日志**。记录失败的 ID、原因、时间戳等详细信息，便于排查问题。`retry` 成功后会删除对应条目。 |
| `.checkpoint.json` | **进度存档**。记录已完成/失败的 ID 列表，用于 `--resume` 断点续传。包含 games 和 reviews 的独立状态。 |

---

<div align="center">
  <p>Made with ❤️ by SeraphinaGlacia / Zhou Xinlei</p>
</div>
