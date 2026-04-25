<div align="center">
  <p align="center">
    <img src="assets/demo.svg" alt="Terminal Demo" width="600">
  </p>

  <h1>Steam Scraper</h1>
  <p>
    <strong>A command-line tool for collecting Steam game metadata and review history.</strong>
  </p>
  <p>
    Built for data analysis, coursework, and exploratory research. It uses AsyncIO, SQLite, and Rich to support step-by-step scraping, checkpoint-based resume, failure logs, and Excel export.
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
> This project includes an AI-agent-oriented guide: [AGENTS.md](AGENTS.md). If you are using Cursor, Antigravity, Claude Code, Codex or another tools, AI can use it to help you operate this program.

## Project Scope

Steam Scraper is a personal open-source project for collecting data from Steam store pages and public endpoints, including:

- Game metadata: AppID, name, release date, price, developers, publishers, genres, and short description.
- Review history: daily cumulative positive and negative recommendation counts.
- Local outputs for later analysis: a SQLite database and an Excel workbook.

It is suitable for coursework, data analysis practice, exploratory research, and small-scale dataset preparation. It is not a distributed crawler framework, a complete Steam API wrapper, or a production-grade scraping system with proxy pools and automated anti-blocking strategies.

---

## Features

- **Asynchronous collection**
  - Uses `asyncio` and `httpx` for concurrent requests.
  - Concurrency, timeout, and retry settings can be adjusted in `config.yaml`.
  - Actual throughput depends on your network, Steam response speed, and rate limits.

- **Structured local storage**
  - Game metadata and review history are stored in SQLite.
  - The schema is intentionally simple so that the data can be queried with SQL or loaded into Pandas.

- **Resume and failure tracking**
  - `.checkpoint.json` records processed and failed AppIDs.
  - `failures.json` keeps failure details for later inspection and retry.
  - The checkpoint mechanism reduces repeated work after interruption, but large runs should still be followed by a failure-log check.

- **Terminal output**
  - Uses Rich for progress bars, messages, and confirmation panels.
  - The primary interface is still the command line.

- **Data export**
  - Supports exporting the SQLite database to an Excel workbook.
  - CSV-related export logic exists in the codebase; if you rely on CSV output, please verify the generated files with the current version.

---

## Quick Start

### 1. Install dependencies

Python 3.10 or later is recommended.

```bash
git clone https://github.com/SeraphinaGlacia/steam-scraper.git
cd steam-scraper
pip install -r requirements.txt
```

### 2. Check the CLI entry point

```bash
python main.py --help
```

You can also run the splash-screen command to verify that dependencies such as Rich and pyfiglet are installed:

```bash
python main.py start
```

### 3. Start with a small test run

Before running a full collection, it is recommended to scrape a small number of pages first and check that networking and database writes work as expected:

```bash
python main.py games --pages 10
python main.py reviews
python main.py export
```

The full workflow can be started with:

```bash
python main.py all
```

If the task is interrupted, resume with:

```bash
python main.py all --resume
```

---

## Commands

### Scrape game metadata: `games`

```bash
python main.py games              # Scrape all pages
python main.py games --pages 10   # Scrape only the first 10 pages for testing
python main.py games --resume     # Resume from checkpoint
```

### Scrape review history: `reviews`

```bash
python main.py reviews            # Scrape review history for games already in the database
python main.py reviews --resume   # Resume from checkpoint
```

You can also provide a text file containing AppIDs:

```bash
python main.py reviews --input appids.txt
```

### Export data: `export`

```bash
python main.py export
```

Default output:

```text
data/steam_data.xlsx
```

### Retry failed tasks: `retry`

```bash
python main.py retry               # Retry all failed tasks
python main.py retry --type game   # Retry only game metadata tasks
python main.py retry --type review # Retry only review-history tasks
```

### Clean and reset: `clean` / `reset`

```bash
python main.py clean    # Clean caches, checkpoints, and temporary files
python main.py reset    # Delete database, exported files, failure logs, and checkpoints
```

> [!CAUTION]
> `reset` deletes generated files under `data/` and cannot be undone. Use it only after confirming that the existing data is no longer needed.

---

## Configuration

Main settings are defined in `config.yaml`:

```yaml
scraper:
  language: english       # Steam store language
  currency: us            # Currency code
  category: "998"         # Category ID; 998 usually refers to Games
  max_workers: 20         # Concurrency; too high may cause rate limits or connection errors

http:
  timeout: 30             # Request timeout in seconds
  max_retries: 3          # Maximum retries for a single request
  min_delay: 0.5          # Minimum delay between requests in seconds
  max_delay: 1.5          # Maximum delay between requests in seconds

output:
  data_dir: ./data
  checkpoint_file: .checkpoint.json
```

If you encounter many `429 Too Many Requests` responses, connection timeouts, or an unusually large number of failures, consider lowering `scraper.max_workers` and retrying failed items later with the `retry` command.

---

## Data Files

After running the scraper, the `data/` directory may contain:

| File | Description |
| :--- | :--- |
| `steam_data.db` | SQLite database containing the `games` and `reviews` tables. |
| `steam_data.xlsx` | Excel workbook containing game metadata and review history sheets. |
| `steam_*.csv` | CSV exports; please verify actual generation behavior with the current version. |
| `failures.json` | Failed-task records, including type, ID, reason, and timestamp. |
| `.checkpoint.json` | Checkpoint state used by `--resume`. |

---

## Known Limitations

- This project is mainly intended for personal learning, coursework, and small-scale data analysis. It should not be treated as a production scraping system as-is.
- It does not include proxy pools, dynamic rate-limit adaptation, CAPTCHA handling, or distributed scheduling.
- Changes in Steam page structure or public endpoints may break parsing.
- Before large-scale runs, test with `--pages` and inspect the failure log afterwards.
- The current codebase uses Python 3.10+ type syntax, so Python 3.10 or later is recommended.

---

<div align="center">
  <p>Made with ❤️ by SeraphinaGlacia / Zhou Xinlei</p>
</div>
