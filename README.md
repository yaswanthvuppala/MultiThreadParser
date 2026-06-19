# Multi-Threaded Web Crawler in Python

This project is a high-performance, concurrent web crawler written in Python. It traverses web pages using a breadth-first search (BFS) strategy, extracts same-domain absolute hyperlinks using BeautifulSoup4, limits crawl depths, and saves page metadata (URL, page title, and crawled timestamp) into a local SQLite database.

## System Architecture

The application is decomposed into three core modules:

1. **Parser Engine (parser.py)**: Manages network requests, HTML page parsing, absolute link resolution, external domain filtering, and the orchestrating BFS crawl loop.
2. **Database Layer (database.py)**: Handles connection initialization, Write-Ahead Logging (WAL) mode setup, and metadata logging to the local SQLite database.
3. **CLI Entry Point (main.py)**: Serves as the command-line interface, accepting configuration parameters (seed URL, depth limits, connection timeouts, and worker counts).

### Concurrency and Thread-Safety Design

Web crawling is an I/O-bound task. To maximize network throughput, this crawler utilizes concurrent workers. The following mechanisms protect shared state and prevent system failures:

* **Worker Pool**: Managed via concurrent.futures.ThreadPoolExecutor, dispatching up to N concurrent threads (defaulting to 5 threads).
* **Task Queue**: Managed via a thread-safe queue.Queue to handle dynamic BFS URL distribution across workers.
* **Visited URL Set Protection**: Protected by a threading.Lock() mutex to prevent race conditions (e.g., multiple workers checking and crawling the same URL simultaneously).
* **SQLite Concurrency Lock**: Python's sqlite3 connections are thread-local and cannot be shared. The DatabaseManager establishes a separate connection per write transaction. Simultaneous writes to the same database file are synchronized using an internal threading.Lock() mutex within the DatabaseManager to completely eliminate SQLite write collisions and database-locked errors.
* **Resilient Worker Loops**: Network timeouts, connection drops, and parsing errors are caught inside the worker thread scope, allowing individual worker failures to resolve gracefully without halting the remaining threads.

---

## Prerequisites

* Python 3.10 or higher
* The `uv` package manager (recommended) or standard `pip`

---

## Setup and Installation

Follow these steps to set up the local virtual environment and install project dependencies:

### 1. Initialize the Virtual Environment

Using uv:
```bash
uv venv
```

Using standard Python:
```bash
python -m venv .venv
```

### 2. Activate the Virtual Environment

On Windows (PowerShell):
```powershell
.venv\Scripts\Activate.ps1
```

On Windows (Command Prompt):
```cmd
.venv\Scripts\activate.bat
```

On macOS/Linux:
```bash
source .venv/bin/activate
```

### 3. Install Dependencies

Using uv:
```bash
uv pip install requests beautifulsoup4
```

Using standard pip:
```bash
pip install requests beautifulsoup4
```

---

## Usage Guide

The crawler is executed via main.py. It requires a seed URL as a positional argument, along with optional parameters.

### Command Syntax

```bash
python main.py <seed_url> [options]
```

### Options

* `seed`: The starting URL (e.g., https://example.com).
* `--depth DEPTH`: Maximum traversal depth (default: 2). A depth of 0 crawls only the seed URL page.
* `--timeout TIMEOUT`: HTTP request connection and read timeout in seconds (default: 5.0).
* `--workers WORKERS`: Number of concurrent worker threads (default: 5).

### Run Examples

#### Example 1: Crawl with default settings (Depth = 2, Workers = 5)
```bash
python main.py https://quotes.toscrape.com
```

#### Example 2: Crawl a custom site with depth 1 and 8 worker threads
```bash
python main.py https://news.ycombinator.com --depth 1 --workers 8
```

#### Example 3: Crawl a site with a custom timeout of 3 seconds
```bash
python main.py https://example.com --depth 2 --timeout 3.0 --workers 4
```

---

## Viewing Crawled Data

When the crawler runs, it creates a local SQLite database named `crawler.db` in the project root directory.

### Table Schema: `crawled_pages`

| Column | Type | Constraints | Description |
|---|---|---|---|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | Unique row identifier |
| url | TEXT | UNIQUE, NOT NULL | Normalized absolute URL |
| title | TEXT | | The extracted HTML <title> tag value |
| timestamp | DATETIME | DEFAULT CURRENT_TIMESTAMP | ISO 8601 timestamp of execution |

### Querying Results via CLI

To inspect the crawled pages stored in the database, execute this quick python query command in your terminal:

```bash
python -c "from database import DatabaseManager; [print(f'URL: {r[1]}\nTitle: {r[2]}\nTimestamp: {r[3]}\n') for r in DatabaseManager().get_all_pages()]"
```

---

## Running Unit Tests

The test suite validates the parsing engine, absolute path conversions, external domain filters, BFS depth configurations, database persistence, and concurrent database lock safety.

Execute all tests using Python's unit test discovery:

```bash
python -m unittest discover
```
