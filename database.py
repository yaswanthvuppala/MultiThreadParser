import sqlite3
import os
import logging
import threading
from datetime import datetime

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Manages the SQLite database for the web crawler.
    
    ### SQLite Multi-Threading Concurrency Documentation:
    
    SQLite is a serverless, file-based database. Because it is file-based, it relies on file-system locks 
    to handle concurrency. In a multi-threaded Python application, SQLite introduces two critical constraints:
    
    1. Connection Isolation (Thread Locality):
       By default, Python's `sqlite3` connections cannot be shared across threads. If Thread A creates a 
       connection, and Thread B attempts to use it, Python raises `sqlite3.ProgrammingError: SQLite objects 
       created in a thread can only be used in that same thread`. This is because the underlying sqlite3 C-API 
       connection handles state sequentially, and interleaving calls from concurrent threads leads to state corruption.
       *Mitigation*: Each thread must instantiate and close its own connection, or we must use a thread-local pool.
       
    2. Write Locking & Operational Errors:
       SQLite supports multiple concurrent readers (especially in WAL - Write-Ahead Logging mode), but only 
       a single writer at any given instant. When a thread initiates a write transaction (INSERT/UPDATE/DELETE), 
       SQLite locks the database file. If another thread attempts a write transaction simultaneously, it receives 
       `sqlite3.OperationalError: database is locked`.
       *Mitigations*:
         - Set a busy-timeout when connecting (e.g. `timeout=30.0` in seconds), forcing SQLite to wait and retry 
           acquiring the lock before failing.
         - Acquire a Mutex lock (`threading.Lock`) within the application layer around database writes.
         - Delegate all database operations to a single database worker thread via a thread-safe Queue (highly recommended 
           for high concurrency).
    """
    
    def __init__(self, db_path: str = "crawler.db"):
        self.db_path = db_path
        self._write_lock = threading.Lock()
        self.initialize_db()

    def get_connection(self) -> sqlite3.Connection:
        """Returns a new SQLite connection.
        
        Setting check_same_thread=False allows advanced handling, but we rely on isolating 
        connections per transaction/call or locking for thread-safety.
        We set a 30-second timeout to mitigate transient lock-contention.
        """
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        # Enable WAL mode for concurrent readers and writers
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def initialize_db(self):
        """Initializes the database and creates tables if they don't exist."""
        query = """
        CREATE TABLE IF NOT EXISTS crawled_pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            title TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """
        conn = None
        try:
            conn = self.get_connection()
            with conn:
                conn.execute(query)
            logger.info("Database initialized successfully.")
        except sqlite3.Error as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
        finally:
            if conn:
                conn.close()

    def save_page(self, url: str, title: str | None) -> bool:
        """Saves a crawled page's metadata to the database.
        
        Uses INSERT OR REPLACE to update title/timestamp if the URL has already been crawled.
        Returns True if successful, False otherwise.
        """
        query = """
        INSERT OR REPLACE INTO crawled_pages (url, title, timestamp)
        VALUES (?, ?, ?);
        """
        now = datetime.now().isoformat()
        conn = None
        with self._write_lock:
            try:
                conn = self.get_connection()
                with conn:
                    conn.execute(query, (url, title, now))
                logger.debug(f"Saved to database: {url}")
                return True
            except sqlite3.Error as e:
                logger.error(f"Error saving page {url} to database: {e}")
                return False
            finally:
                if conn:
                    conn.close()

    def get_all_pages(self) -> list[tuple]:
        """Retrieves all crawled page records from the database.
        
        Returns a list of tuples: (id, url, title, timestamp)
        """
        query = "SELECT id, url, title, timestamp FROM crawled_pages ORDER BY id ASC;"
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(query)
            return cursor.fetchall()
        except sqlite3.Error as e:
            logger.error(f"Error retrieving pages: {e}")
            return []
        finally:
            if conn:
                conn.close()
