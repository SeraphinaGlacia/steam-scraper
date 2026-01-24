<div align="center">
  <p align="center">
    <img src="assets/demo.svg" alt="Terminal Demo" width="600">
  </p>
  <h1>Simple Steam Scraper</h1>
  <p>
    <strong>A high-performance Steam data scraper based on Python, bringing you an ultimate data scraping experience.</strong>
  </p>
  <p>
    Not just powerful, but elegant. Immersive TUI built with <code>Rich</code>, making data collection no longer boring.
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

> [!WARNING]
> This documentation is translated from Chinese using Gemini and may not be completely accurate.

---

## ✨ Core Features

- **🎨 Ultimate Terminal UI Experience**
    - Say goodbye to scrolling plain text logs, embrace **Panels**, **Tables**, and **Progress Bars**.
    - Key information is highlighted, error logs are clear and readable, making the scraper's running status clear at a glance.
    - Includes a cool ASCII Art splash screen for that extra ritualistic feel.

- **🚀 High-Performance Concurrent Scraping**
    - Built-in `ThreadPoolExecutor` supports high-concurrency scraping with **10x+** speed.
    - Smart rate limiting and retry mechanisms find the perfect balance between speed and stability.

- **🛡️ Robust Resume Capability**
    - Unexpected power outage? Network interruption? No worries!
    - Progress is saved in real-time. Resume seamlessly from where you left off with the `--resume` command, refusing repetitive work.

- **🗄️ Enterprise-Grade Data Management**
    - **SQLite Storage**: Not simple CSV, but a relational database with rigorous structure and efficient querying.
    - **One-Click Export**: Supports exporting all data (game basic info + history reviews) into perfectly formatted **Excel** reports.

- **🔄 Smart Failure Retry**
    - Automatically captures all failed task IDs and reasons.
    - Provides an interactive retry command `retry` to precisely target failed items, ensuring 100% data integrity.

---

## 🛠️ Quick Start

### 1. Install Dependencies

Ensure your Python version is >= 3.8.

```bash
git clone https://github.com/SeraphinaGlacia/simple-steam-scraper.git
cd simple-steam-scraper
pip install -r requirements.txt
```

### 2. Experience the Cool Splash Screen (Easter Egg 🎪)

We hid this command in the help menu, and although it has no practical function, you can run it directly to test your environment configuration and admire the splash screen:

```bash
python main.py start
```

### 3. Standard Workflow

The most commonly used fully automated one-stop service:

```bash
# 1. Start the complete scraping task (Game Info -> Review History -> Export Excel)
python main.py all

# 2. If the task is interrupted, resume progress
python main.py all --resume
```

---

## 📖 Detailed Command Guide

Our CLI design follows the UNIX philosophy, providing rich subcommands:

### 🎮 Scrape Game Info (`games`)

Scrape only the basic game data from the Steam store (price, developer, positive rating rate, etc.).

```bash
python main.py games              # Scrape all pages
python main.py games --pages 10   # Scrape only the first 10 pages (suitable for testing)
python main.py games --resume     # Continue from the last interruption
```

### 📝 Scrape Review History (`reviews`)

For games whose basic information has already been written to the database, scrape their historical review trend data.

```bash
python main.py reviews            # Scrape reviews for all games in the database
python main.py reviews --resume   # Resume from breakpoint
```

### 📤 Export Data (`export`)

Export the content of the SQLite database to an Excel file.

```bash
python main.py export
# The output file is located at data/steam_data.xlsx by default
```

### 🔄 Retry Failures (`retry`)

The program automatically records all failed requests. Failures caused by network fluctuations can be fixed with one click using this command.

```bash
python main.py retry              # Retry all failed tasks
python main.py retry --type game  # Retry only game info tasks
```

### 🧹 Maintenance & Cleanup (`clean` / `reset`)

Keep the project clean.

> [!CAUTION]
> The `reset` command will delete ALL data, including the database, exported files, failure logs, etc., and CANNOT be recovered!

```bash
python main.py clean    # Clean up Python cache, checkpoint files, and other temporary files
python main.py reset    # ⚠️ [DANGER] Delete database and all data, reset to initial state
```

---

## ⚙️ Configuration

All magic is defined in `config.yaml`, which you can customize as you wish:

```yaml
scraper:
  language: english       # Steam store language
  currency: us            # Currency code
  category: "998"         # Category ID (998 is for games)
  max_workers: 10         # Concurrent threads (Default is 10, too high may lead to IP ban)

http:
  timeout: 30             # Request timeout (seconds)
  max_retries: 3          # Maximum retry attempts
  min_delay: 1.0          # Minimum request interval (seconds)
  max_delay: 3.0          # Maximum request interval (seconds)

output:
  data_dir: ./data        # Data output directory
  checkpoint_file: .checkpoint.json  # Checkpoint file
```

---

## 📂 Data Structure

After running, the `data/` directory will contain:

| File | Description |
| :--- | :--- |
| `steam_data.db` | **Core Database** (SQLite). Contains `games` and `reviews` tables, suitable for direct query by developers. |
| `steam_data.xlsx` | **Final Report**. Contains two Sheets, allowing data analysis without writing code. |
| `failures.json` | **Failure Log**. Records failed IDs, reasons, timestamps, and other details for troubleshooting. Entries are removed after successful `retry`. |
| `.checkpoint.json` | **Progress Save**. Records completed/failed ID lists for `--resume` capability. Contains independent states for games and reviews. |

---

<div align="center">
  <p>Made with ❤️ by SeraphinaGlacia / Zhou Xinlei</p>
</div>
