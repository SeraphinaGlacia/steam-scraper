<div align="center">
  <p align="center">
    <img src="assets/demo.svg" alt="Terminal Demo" width="600">
  </p>

  <h1>Steam Scraper</h1>
  <p>
    <strong>用于采集 Steam 游戏基础信息与评价历史的命令行工具。</strong>
  </p>
  <p>
    面向数据分析与课程/研究练习场景，基于 AsyncIO、SQLite 和 Rich 构建，支持分步采集、断点恢复、失败记录与 Excel 导出。
  </p>

  <p>
    <a href="LICENSE"><img src="https://img.shields.io/github/license/SeraphinaGlacia/steam-scraper?style=flat-square" alt="License"></a>
    <img src="https://img.shields.io/badge/python-3.10+-blue?style=flat-square&logo=python&logoColor=white" alt="Python Version">
    <img src="https://img.shields.io/github/repo-size/SeraphinaGlacia/steam-scraper?style=flat-square" alt="Repo Size">
    <img src="https://img.shields.io/badge/arch-AsyncIO-green?style=flat-square" alt="Architecture">
  </p>

  <p>
    <a href="README_EN.md">English</a> • 
    <a href="README.md">中文</a>
    <br>
  </p>
</div>

---

> [!TIP]
> 本项目包含一份面向智能体的 [AGENTS.md](AGENTS.md) 操作说明。如果你正在使用 Cursor、Antigravity、Claude Code、Codex 或其他工具，AI 可以通过其帮助你操作本程序。

## 项目定位

Steam Scraper 是一个个人开源项目，主要用于从 Steam 商店页面和公开接口中采集：

- 游戏基础信息：AppID、名称、发行日期、价格、开发商、发行商、类型和简介等；
- 评价历史数据：按日期记录的好评/差评累计数据；
- 可供后续分析使用的 SQLite 数据库和 Excel 报表。

它适合用于课程作业、数据分析练习、探索性研究或小规模数据整理。它不是分布式爬虫框架，也不包含代理池、自动反封锁策略或完整的 Steam API 封装。

---

## 主要功能

- **异步采集**
  - 使用 `asyncio` 与 `httpx` 发起并发请求。
  - 并发数、请求超时和重试次数可通过 `config.yaml` 调整。
  - 实际速度会受到网络环境、Steam 响应速度和访问频率限制影响。

- **结构化存储**
  - 游戏信息与评价历史会写入 SQLite 数据库。
  - 数据表结构较简单，便于使用 SQL 或 Pandas 继续分析。

- **断点恢复与失败记录**
  - 使用 `.checkpoint.json` 记录已处理和失败的 AppID。
  - 使用 `failures.json` 保存失败原因，便于后续通过 `retry` 命令重试。
  - 断点机制用于降低中断后的重复工作量，但仍建议在大规模运行后检查失败记录。

- **终端输出**
  - 基于 Rich 提供进度条、提示信息和确认面板。
  - 主要交互方式仍然是命令行。

- **数据导出**
  - 支持将 SQLite 数据导出为 Excel 文件。
  - 代码中包含 CSV 导出相关逻辑；如果依赖 CSV 结果，请在当前版本中运行后检查生成文件是否符合预期。

---

## 快速开始

### 1. 安装依赖

建议使用 Python 3.10 或更高版本。

```bash
git clone https://github.com/SeraphinaGlacia/steam-scraper.git
cd steam-scraper
pip install -r requirements.txt
```

### 2. 检查命令行入口

```bash
python main.py --help
```

也可以运行启动页命令，确认 Rich 和 pyfiglet 等依赖已安装：

```bash
python main.py start
```

### 3. 先用少量页面测试

在正式运行全量采集前，建议先抓取少量页面，确认网络和数据写入正常：

```bash
python main.py games --pages 10
python main.py reviews
python main.py export
```

完整流程可以使用：

```bash
python main.py all
```

如果任务中断，可以使用：

```bash
python main.py all --resume
```

---

## 命令说明

### 抓取游戏基础信息：`games`

```bash
python main.py games              # 抓取所有分页
python main.py games --pages 10   # 只抓取前 10 页，适合测试
python main.py games --resume     # 从断点继续
```

### 抓取评价历史：`reviews`

```bash
python main.py reviews            # 抓取数据库中已有游戏的评价历史
python main.py reviews --resume   # 从断点继续
```

也可以指定包含 AppID 的文本文件：

```bash
python main.py reviews --input appids.txt
```

### 导出数据：`export`

```bash
python main.py export
```

默认输出：

```text
data/steam_data.xlsx
```

### 重试失败任务：`retry`

```bash
python main.py retry              # 重试所有失败任务
python main.py retry --type game  # 只重试游戏信息任务
python main.py retry --type review # 只重试评价历史任务
```

### 清理与重置：`clean` / `reset`

```bash
python main.py clean    # 清理缓存、断点和临时文件
python main.py reset    # 删除数据库、导出文件、失败日志和断点文件
```

> [!CAUTION]
> `reset` 会删除 `data/` 目录下的运行结果，操作不可恢复。请确认不再需要已有数据后再使用。

---

## 配置说明

主要配置位于 `config.yaml`：

```yaml
scraper:
  language: english       # Steam 商店语言
  currency: us            # 货币代码
  category: "998"         # 分类 ID，998 通常表示 Games
  max_workers: 20         # 并发数，过高可能触发限流或连接错误

http:
  timeout: 30             # 请求超时，单位：秒
  max_retries: 3          # 单次请求最大重试次数
  min_delay: 0.5          # 请求间隔最小值，单位：秒
  max_delay: 1.5          # 请求间隔最大值，单位：秒

output:
  data_dir: ./data
  checkpoint_file: .checkpoint.json
```

如果遇到大量 `429 Too Many Requests`、连接超时或失败记录明显增多，建议降低 `scraper.max_workers`，并在稍后使用 `retry` 命令补抓失败项目。

---

## 数据结构

运行后，`data/` 目录可能包含：

| 文件 | 说明 |
| :--- | :--- |
| `steam_data.db` | SQLite 数据库，包含 `games` 和 `reviews` 两张表。 |
| `steam_data.xlsx` | Excel 导出文件，包含游戏信息和评价历史两个 Sheet。 |
| `steam_*.csv` | CSV 导出文件；请根据当前版本实际生成情况检查。 |
| `failures.json` | 失败任务记录，包含失败类型、ID、原因和时间戳。 |
| `.checkpoint.json` | 断点记录，用于 `--resume` 恢复任务。 |

---

## 已知限制

- 当前项目主要面向个人学习、课程作业和小规模数据分析，不建议作为生产级采集系统直接使用。
- 项目没有内置代理池、动态限流、验证码处理或分布式调度能力。
- Steam 页面结构或公开接口变化可能导致解析失败。
- 大规模采集前建议先用 `--pages` 做小样本测试，并在结束后检查失败日志。
- 当前源码使用了 Python 3.10+ 的类型语法，因此建议使用 Python 3.10 或更高版本运行。

---

<div align="center">
  <p>Made with ❤️ by SeraphinaGlacia / Zhou Xinlei</p>
</div>
