<div align="center">
  <h1>Simple Steam Scraper</h1>
  <p>
    A lightweight, modular, and resumable Steam game data scraper based on Python.<br>
    Designed to help data analysis enthusiasts or researchers quickly obtain basic information and historical review trends of Steam store games.
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

> [!WARNING]
> This documentation was translated by Gemini. I cannot guarantee its complete accuracy.
> 
> 本文档由 Gemini 翻译，无法保证其完全准确。

## ✨ Features

- 🎮 **Scrape Steam Store Game Info** (Name, Price, Developer, Genre, etc.)
- 📊 **Scrape Review History** (Positive/Negative reviews by date)
- ⚡️ **High Concurrency**, 10x faster speed
- 🗄️ **SQLite Storage**, efficient and stable
- 💾 **Export to Excel**, one-click export for all data
- ⏸️ **Resume Capability**, continue from where you left off
- 🔄 **Auto Retry**, handles failures automatically
- ⚙️ **Configurable**, adapt to different network environments

## 🚀 Quick Start

### 0. Get the Code

1.  **Open Command Line Tool**:
    *   **Windows**: Press `Win + R`, type `cmd`, and press Enter.
    *   **Mac**: Open `Terminal`.

2.  **Clone Repository**:
    Enter the following command in the terminal to download the code:
    ```bash
    git clone https://github.com/SeraphinaGlacia/simple-steam-scraper.git
    ```

3.  **Enter Project Directory**:
    ```bash
    cd simple-steam-scraper
    ```

### 1. 📦 Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. 📖 View Help

```bash
python main.py --help
```

### 3. 🕸️ Scrape All Games (Recommended - Full Flow)

```bash
# Scrape all game info + review history (automatically gets total pages)
python main.py all

# If interrupted, resume from checkpoint
python main.py all --resume
```

### 4. 🪜 Run Step by Step (Advanced)

```bash
# Step 1: Scrape basic game info
python main.py games              # Scrape all pages
python main.py games --pages 100  # Scrape only the first 100 pages

# Step 2: Scrape review history (based on app_id list from Step 1)
python main.py reviews
```

### 5. 🧹 Clean Cache and Temp Files

```bash
python main.py clean
```

### 6. 🔄 Retry Failures

If network errors occur during scraping, the program automatically records failed items. Use the following commands to retry:

```bash
# Retry all failed items (games + reviews)
python main.py retry

# Retry only failed game info
python main.py retry --type game

# Retry only failed review history
python main.py retry --type review
```

### 7. 🗑️ Reset Project

> [!CAUTION]
> IRREVERSIBLE ACTION!

To clear ALL scraped data (Database, Excel) and cache files to start over:

```bash
python main.py reset
```

The program will ask for double confirmation to prevent accidental data loss.

### 8. 📤 Export Data

Export data from database to Excel file (includes two sheets):

```bash
python main.py export
```



### 9. 📂 Output Files

All data files are saved in the `data/` directory:

| File | Description |
|------|-------------|
| `data/steam_data.db` | SQLite database file (Core Data) |
| `data/steam_data.xlsx` | Exported Excel file (Contains Games & Reviews) |

## 🏗️ Project Structure

```
simple_steam_scraper/
├── src/                          # Core Modules
│   ├── config.py                 # Configuration Management
│   ├── models.py                 # Data Models
│   ├── scrapers/                 # Scraper Modules
│   │   ├── game_scraper.py       # Game Info Scraper
│   │   └── review_scraper.py     # Review History Scraper
│   ├── database.py               # Database Management
│   └── utils/                    # Utility Modules
│       ├── http_client.py        # HTTP Client
│       ├── checkpoint.py         # Checkpoint Management
│       └── failure_manager.py    # Failure Recording Manager
├── data/                         # Data Output Directory
├── config.yaml                   # Configuration File
├── main.py                       # Unified Entry Point
├── README.md                     # Chinese Documentation
└── README_EN.md                  # English Documentation
```

## ⚙️ Configuration

Edit `config.yaml` to customize scraper behavior:

```yaml
scraper:
  language: english    # Steam Store Language
  currency: us         # Currency Code
  category: "998"      # Category ID (998 is for Games)
  max_workers: 10      # Concurrency Threads (Default 10)

http:
  timeout: 30          # Request Timeout (seconds)
  max_retries: 3       # Max Retries
  min_delay: 1.0       # Min Request Delay (seconds)
  max_delay: 3.0       # Max Request Delay (seconds)

output:
  data_dir: ./data        # Data Output Directory
  checkpoint_file: .checkpoint.json  # Breakpoint File
```

## 🧩 Appendix: How It Works

This program automates the collection and integration of Steam game data by simulating user browsing and querying data interfaces. The core process and file interactions are as follows:

1.  **Concurrent Scraping & Storage**
    - The program uses multi-threading (`ThreadPoolExecutor`) to concurrently access Steam search pages and APIs.
    - **Game Info**: Scraped basic game info (id, name, price, etc.) is saved in real-time to the SQLite database `games` table.
    - **Review History**: Review history data for each game is scraped concurrently and saved to the `reviews` table.
    - **Resume Capability**: intelligently skips collected items using database primary keys and `checkpoint` mechanism.

2.  **Data Export**
    - After scraping, use the `export` command to read all data from the database.
    - **Output File**: Generates an Excel file (`data/steam_data.xlsx`) containing `Games` and `Reviews` sheets for easy analysis.



---

<div align="center">
  <p>MIT License © 2025</p>
</div>
