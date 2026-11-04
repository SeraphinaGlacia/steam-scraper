<div align="center">
  <p align="center">
    <img src="assets/demo.svg" alt="Terminal Demo" width="600">
  </p>

  <h1>Steam Scraper</h1>
  <p>
    <strong>A command-line tool for collecting Steam game metadata and review history.</strong>
  </p>
  <p>
    Built for data analysis, coursework, and exploratory research. It uses AsyncIO, SQLite, and Rich to support step-by-step scraping, checkpoint-based resume, failure logs, and Excel/CSV export.
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
  - Exports the SQLite database to an Excel workbook or two CSV files.
  - CSV output uses `utf-8-sig` encoding for convenient use with Excel and Pandas.

---

## Quick Start

### 1. Create and sync the environment

The project uses [uv](https://docs.astral.sh/uv/getting-started/installation/) to manage Python, dependencies, the virtual environment, and the lockfile. Install uv first; the repository's `.python-version` lets uv select Python 3.10 automatically.

```bash
git clone https://github.com/SeraphinaGlacia/steam-scraper.git
cd steam-scraper
uv sync --locked
```

### 2. Check the CLI entry point

```bash
uv run steam-scraper --help
```

You can also run the splash-screen command to verify the environment:

```bash
uv run steam-scraper start
```

### 3. Start with a small test run

Before running a full collection, it is recommended to scrape a small number of pages first and check that networking and database writes work as expected:

```bash
uv run steam-scraper games --pages 10
uv run steam-scraper reviews
uv run steam-scraper export
```

The full workflow can be started with:

```bash
uv run steam-scraper all
```

If the task is interrupted, resume with:

```bash
uv run steam-scraper all --resume
```

---

## Commands

### Scrape game metadata: `games`

```bash
uv run steam-scraper games              # Scrape all pages
uv run steam-scraper games --pages 10   # Scrape the first 10 pages for testing
uv run steam-scraper games --resume     # Resume from checkpoint
```

### Scrape review history: `reviews`

```bash
uv run steam-scraper reviews            # Scrape reviews for games in the database
uv run steam-scraper reviews --resume   # Resume from checkpoint
```

You can also provide a text file containing AppIDs:

```bash
uv run steam-scraper reviews --input appids.txt
```

### Export data: `export`

```bash
uv run steam-scraper export                # Export Excel
uv run steam-scraper export --format csv   # Export CSV
```

Default output:

```text
data/steam_data.xlsx
```

### Retry failed tasks: `retry`

```bash
uv run steam-scraper retry               # Retry all failed tasks
uv run steam-scraper retry --type game   # Retry only game metadata tasks
uv run steam-scraper retry --type review # Retry only review-history tasks
```

### Clean and reset: `clean` / `reset`

```bash
uv run steam-scraper clean    # Clean caches, checkpoints, and temporary files
uv run steam-scraper reset    # Delete data, exports, failure logs, and checkpoints
```

> [!CAUTION]
> `reset` deletes generated files under `data/` and cannot be undone. Use it only after confirming that the existing data is no longer needed.

---

## Development and quality checks

Ruff, ty, pytest, and pytest-cov live in development dependency groups and are not runtime dependencies of the built package. After changing code, run:

```bash
uv sync --locked --all-groups
uv run ruff format --check .
uv run ruff check .
uv run ty check src
uv run pytest
uv build --no-sources
```

The project uses a `src/steam_scraper` package layout. Dependencies and tool settings live in `pyproject.toml`, while `uv.lock` records reproducible versions.

---

## Configuration

The root-level `config.yaml` is the program's user-facing configuration file. It is loaded automatically on startup; save your changes and run the same command without extra flags or initialization steps.

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
  max_connections: 100    # Maximum HTTP pool connections
  max_keepalive_connections: 20  # Maximum idle connections
  user_agent: "Mozilla/5.0 ..."  # User-Agent sent to Steam

output:
  data_dir: ./data                   # Directory for all generated data
  database_file: steam_data.db       # SQLite database filename
  checkpoint_file: .checkpoint.json  # Checkpoint filename
  failure_log_file: failures.json    # Failure-log filename
```

Changing `output.data_dir` moves the database, checkpoint, failure log, and default Excel/CSV exports together. The database, checkpoint, and failure-log filenames are configured in the same section.

If you encounter many `429 Too Many Requests` responses, connection timeouts, or an unusually large number of failures, consider lowering `scraper.max_workers` and retrying failed items later with the `retry` command.

---

## Data Files

After running the scraper, the directory selected by `output.data_dir` (`data/` by default) may contain:

| File | Description |
| :--- | :--- |
| `steam_data.db` | SQLite database containing the `games` and `reviews` tables. |
| `steam_data.xlsx` | Excel workbook containing game metadata and review history sheets. |
| `steam_games.csv`, `steam_reviews.csv` | Game and review CSV files produced with `--format csv`. |
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

## Review granularity

Review exports include `granularity` to distinguish daily, weekly, and monthly buckets. See [data semantics and migration](docs/review-data.md#english).
