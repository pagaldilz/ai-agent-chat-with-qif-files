import os
import sqlite3


def test_master_tables_exist():
    db_path = os.getenv('DB_PATH', '/db/transactions.db')
    assert os.path.exists(db_path), f"DB not found at {db_path}. Rebuild should create it."
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cur.fetchall()}
    conn.close()

    # Existing
    assert 'transactions' in tables
    # New master tables
    for t in ['categories', 'tags', 'securities', 'prices', 'memorized']:
        assert t in tables, f"Missing table {t}"
 