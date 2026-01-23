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

- 🎮 **Scrape Game Basic Info**: Name, price, developer, genre, etc.
- 📊 **Scrape Review History**: Positive/Negative review counts categorized by date.
- 💾 **Export to Excel**: Data saved as .xlsx files.
- ⏸️ **Resumable**: Supports stopping and resuming from where you left off.
- 🔄 **Auto-Retry**: Automatically records failures and supports retrying.
- ⚙️ **Configurable**: Adjustable request parameters.

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

### 7. 📂 Output Files

All data files are saved in the `data/` directory:

| File | Description |
|------|-------------|
| `steam_games_{timestamp}.xlsx` | Game basic info |
| `steam_appids.txt` | List of Game IDs |
| `steam_recommendations_data/` | Review history for each game |

## 🏗️ Project Structure

```
simple_steam_scraper/
├── src/                          # Core Modules
│   ├── config.py                 # Configuration Management
│   ├── models.py                 # Data Models
│   ├── scrapers/                 # Scraper Modules
│   │   ├── game_scraper.py       # Game Info Scraper
│   │   └── review_scraper.py     # Review History Scraper
│   ├── exporters/                # Export Modules
│   │   └── excel.py              # Excel Export
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

http:
  timeout: 30          # Request Timeout (seconds)
  max_retries: 3       # Max Retries
  min_delay: 1.0       # Min Request Delay (seconds)
  max_delay: 3.0       # Max Request Delay (seconds)

output:
  data_dir: ./data     # Data Output Directory
```

## 🧩 Appendix: How It Works

This program automates the collection and integration of Steam game data by simulating user browsing and querying data interfaces. The core process and file interactions are as follows:

1.  **Traverse and Generate App ID List**
    - The program first visits the Steam search page, traverses the game list under the specified category, and parses the HTML structure to extract basic metadata (App ID).
    - **Output File**: Extracted IDs are written in real-time to `data/steam_appids.txt`, serving as an index list for subsequent steps.

2.  **Fetch Game Details**
    - The program reads the list generated in the previous step (or uses data directly from memory) and calls the Steam Store API interface to batch fetch detailed game information (id, name, release_date, price, developers, etc.).
    - **Output File**: All basic information is structured and saved as `data/steam_games_{timestamp}.xlsx`, which is the master table for basic game data.

3.  **Fetch Game Review History**
    - For each App ID in the list, the program further requests the Steam Review Histogram API to obtain review trend data since release.
    - **Output File**: Review history data for each game is saved in the `data/steam_recommendations_data/` directory. The folder contains multiple `.xlsx` files named `steam_recommendations_{AppID}.xlsx`, each recording the positive/negative review data for the corresponding game over different time spans.

4.  **Completion**
    - Finally, the program ensures that all collected information (basic details + review history) is completely saved, facilitating direct reading by subsequent analysis tools.

---

<div align="center">
  <p>MIT License © 2025</p>
</div>
