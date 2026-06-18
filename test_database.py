import unittest
import os
import sqlite3
from database import DatabaseManager

class TestDatabaseManager(unittest.TestCase):
    def setUp(self):
        self.db_path = "test_crawler.db"
        # Ensure we start fresh
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        self.db = DatabaseManager(self.db_path)

    def tearDown(self):
        # Clean up database files
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except OSError:
                pass
        # Clean up WAL files if SQLite created them
        wal_path = f"{self.db_path}-wal"
        shm_path = f"{self.db_path}-shm"
        for path in (wal_path, shm_path):
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

    def test_database_initialization(self):
        # Verify database file is created
        self.assertTrue(os.path.exists(self.db_path))
        
        # Verify table structure
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='crawled_pages';")
        table = cursor.fetchone()
        self.assertIsNotNone(table)
        self.assertEqual(table[0], "crawled_pages")
        conn.close()

    def test_save_and_retrieve_page(self):
        # Insert a page
        success = self.db.save_page("https://example.com/page1", "Page One Title")
        self.assertTrue(success)

        # Retrieve and verify
        records = self.db.get_all_pages()
        self.assertEqual(len(records), 1)
        # Record format: (id, url, title, timestamp)
        self.assertEqual(records[0][1], "https://example.com/page1")
        self.assertEqual(records[0][2], "Page One Title")
        self.assertIsNotNone(records[0][3])

    def test_duplicate_url_replace(self):
        # Save initially
        self.db.save_page("https://example.com/dup", "Initial Title")
        # Save again with new title
        self.db.save_page("https://example.com/dup", "Updated Title")

        # Verify replacement occurred instead of inserting a new record
        records = self.db.get_all_pages()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0][1], "https://example.com/dup")
        self.assertEqual(records[0][2], "Updated Title")

    def test_concurrent_database_writes(self):
        import threading
        
        num_threads = 10
        writes_per_thread = 10
        threads = []
        errors = []

        def worker(thread_idx):
            for i in range(writes_per_thread):
                url = f"https://example.com/thread_{thread_idx}_write_{i}"
                title = f"Title {thread_idx} {i}"
                try:
                    success = self.db.save_page(url, title)
                    if not success:
                        errors.append(f"Thread {thread_idx} write {i} returned False")
                except Exception as e:
                    errors.append(f"Thread {thread_idx} write {i} raised exception: {e}")

        # Spawn threads
        for t in range(num_threads):
            thread = threading.Thread(target=worker, args=(t,))
            threads.append(thread)
            thread.start()

        # Join threads
        for thread in threads:
            thread.join()

        # Verify no errors occurred
        self.assertEqual(len(errors), 0, f"Concurrent database write errors: {errors}")

        # Verify total rows written
        records = self.db.get_all_pages()
        self.assertEqual(len(records), num_threads * writes_per_thread)


if __name__ == "__main__":
    unittest.main()
