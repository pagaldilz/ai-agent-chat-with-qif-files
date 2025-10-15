import os
import re
import pandas as pd
import logging
from sqlalchemy import create_engine, Column, Float, String, Date, MetaData, Table, Index, Integer, text
from datetime import date, datetime

class QIFIndexer:
    def __init__(self, qif_dir: str, db_path: str):
        self.qif_dir = qif_dir
        self.db_path = db_path
        self.logger = logging.getLogger('qif_indexer')
        self.logger.setLevel(logging.INFO)
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
            echo=True
        )
        self.metadata = MetaData()
        self.transactions = Table(
            'transactions', self.metadata,
            Column('id', Integer, primary_key=True, autoincrement=True),
            Column('date', Date),
            Column('payee', String),
            Column('category', String),
            Column('memo', String),
            Column('amount', Float),
            Column('source_file', String),
            Column('account_name', String),
            Column('account_type', String),
            # Indexes for common filters
            sqlite_autoincrement=False,
        )
        # Define indexes (created in build_database when metadata.create_all runs)
        Index('ix_transactions_date', self.transactions.c.date)
        Index('ix_transactions_category', self.transactions.c.category)
        Index('ix_transactions_payee', self.transactions.c.payee)

    def create_analyzer_tables(self):
        """Create all analyzer tables if they don't exist."""
        # Recurring transactions table
        recurring_sql = """
        CREATE TABLE IF NOT EXISTS recurring_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            merchant_pattern TEXT,
            amount_avg REAL,
            amount_std REAL,
            frequency_days REAL,
            frequency_category TEXT,
            last_seen TEXT,
            next_expected TEXT,
            confidence_score REAL,
            transaction_count INTEGER,
            category TEXT,
            account_name TEXT,
            account_type TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        
        # Merchants table
        merchants_sql = """
        CREATE TABLE IF NOT EXISTS merchants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_name TEXT UNIQUE NOT NULL,
            original_name TEXT,
            transaction_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        
        # Budgets table
        budgets_sql = """
        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            period TEXT NOT NULL,
            amount REAL NOT NULL,
            start_date TEXT,
            end_date TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        
        # Goals table
        goals_sql = """
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            target_amount REAL NOT NULL,
            current_amount REAL DEFAULT 0,
            deadline TEXT,
            category TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        
        # Transfers table
        transfers_sql = """
        CREATE TABLE IF NOT EXISTS transfers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_transaction_id INTEGER,
            to_transaction_id INTEGER,
            from_account TEXT,
            to_account TEXT,
            amount REAL,
            transfer_date TEXT,
            confidence_score REAL,
            detection_method TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (from_transaction_id) REFERENCES transactions (id),
            FOREIGN KEY (to_transaction_id) REFERENCES transactions (id)
        )
        """
        
        # Anomalies table
        anomalies_sql = """
        CREATE TABLE IF NOT EXISTS anomalies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id INTEGER,
            anomaly_type TEXT,
            score REAL,
            explanation TEXT,
            date TEXT,
            payee TEXT,
            amount REAL,
            category TEXT,
            account_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (transaction_id) REFERENCES transactions (id)
        )
        """
        
        with self.engine.connect() as conn:
            conn.execute(text(recurring_sql))
            conn.execute(text(merchants_sql))
            conn.execute(text(budgets_sql))
            conn.execute(text(goals_sql))
            conn.execute(text(transfers_sql))
            conn.execute(text(anomalies_sql))
            conn.commit()
        
        self.logger.info("Created all analyzer tables")

    def parse_qif_date(self, qif_date_str):
            """
            Parse QIF date like '4/11'2004' and return a Python date object in yyyy-mm-dd format.
            Logs and returns None if parsing fails.
            """
            try:
                # Normalize whitespace
                q = qif_date_str.strip()
                # Handle mm/dd'yyyy or mm/d'yy (two-digit year) formats
                if "'" in q:
                    parts = q.split("'")
                    if len(parts) == 2:
                        mmdd, yy_or_yyyy = parts
                        month, day = [int(x) for x in mmdd.split('/')]
                        # Two-digit year handling with 1970-2069 pivot
                        if len(yy_or_yyyy) == 2:
                            yy = int(yy_or_yyyy)
                            year = 1900 + yy if yy >= 70 else 2000 + yy
                        else:
                            year = int(yy_or_yyyy)
                        return date(year, month, day)
                # Fallbacks: mm/dd/yyyy, mm/d/yy, m/d/yy
                for fmt in ("%m/%d/%Y", "%m/%d/%y", "%m/%e/%Y", "%m/%e/%y"):
                    try:
                        return datetime.strptime(q, fmt).date()
                    except Exception:
                        pass
                # If nothing matched, raise to be caught below
                raise ValueError("Unsupported QIF date format")
            except Exception as e:
                self.logger.warning(f"Bad date format: {qif_date_str} ({e})")
                return None

    def parse_qif(self) -> pd.DataFrame:
            """
            Parse all .qif files in the directory and return a Pandas DataFrame.
            """
            records = []
            files = [f for f in os.listdir(self.qif_dir) if f.lower().endswith('.qif')]
            self.logger.info(f"Found {len(files)} QIF file(s): {files}")
            for fname in files:
                path = os.path.join(self.qif_dir, fname)
                self.logger.info(f"Parsing QIF file: {path}")
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    current = {}
                    current_account = {'name': '', 'type': ''}
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        # Handle account headers
                        if line.startswith('!Account'):
                            # Account name follows
                            continue
                        elif line.startswith('!Type:'):
                            # Account type (Bank, Credit Card, Investment, etc.)
                            current_account['type'] = line[6:]  # Remove '!Type:'
                            continue
                        elif line.startswith('N'):
                            # Account name
                            current_account['name'] = line[1:]
                            continue
                        elif line == '^':
                            # Process and store transaction
                            # Date
                            dt = self.parse_qif_date(current.get('date', '')) if 'date' in current else None
                            # Amount
                            amt = 0.0
                            if 'amount' in current:
                                try:
                                    amt = float(current['amount'].replace(',', ''))
                                except Exception as e:
                                    self.logger.warning(f"Bad amount: {current['amount']} in file {fname} ({e})")
                                    amt = 0.0
                            records.append({
                                'date': dt,
                                'payee': current.get('payee', ''),
                                'category': current.get('category', ''),
                                'memo': current.get('memo', ''),
                                'amount': amt,
                                'source_file': fname,
                                'account_name': current_account['name'],
                                'account_type': current_account['type'],
                            })
                            current = {}
                        elif line.startswith('D'):
                            current['date'] = line[1:]
                        elif line.startswith('T'):
                            current['amount'] = line[1:]
                        elif line.startswith('P'):
                            current['payee'] = line[1:]
                        elif line.startswith('L'):
                            current['category'] = line[1:]
                        elif line.startswith('M'):
                            current['memo'] = line[1:]
                    # Handle final record if file doesn't end with ^
                    if current:
                        dt = self.parse_qif_date(current.get('date', '')) if 'date' in current else None
                        amt = 0.0
                        if 'amount' in current:
                            try:
                                amt = float(current['amount'].replace(',', ''))
                            except Exception as e:
                                self.logger.warning(f"Bad amount: {current['amount']} in file {fname} ({e})")
                                amt = 0.0
                        records.append({
                            'date': dt,
                            'payee': current.get('payee', ''),
                            'category': current.get('category', ''),
                            'memo': current.get('memo', ''),
                            'amount': amt,
                            'source_file': fname,
                            'account_name': current_account['name'],
                            'account_type': current_account['type'],
                        })
            self.logger.info(f"Parsed total {len(records)} transactions")
            df = pd.DataFrame(records)
            return df    

    def build_database(self):
        self.logger.info("Building SQLite database from parsed transactions")
        df = self.parse_qif()
        self.logger.info(f"DataFrame shape: {df.shape}")
        # Drop and recreate table
        self.metadata.drop_all(self.engine, checkfirst=True)
        self.metadata.create_all(self.engine)
        # Create analyzer tables
        self.create_analyzer_tables()
        # Populate
        df.to_sql('transactions', self.engine, if_exists='append', index=False)
        self.logger.info("Database build complete")

    def ensure_database(self):
        """Ensure the database file exists and is populated."""
        if not os.path.exists(self.db_path) or os.path.getsize(self.db_path) == 0:
            self.logger.info(f"Database file {self.db_path} missing or empty; creating.")
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            self.build_database()
        else:
            self.logger.info(f"Database file {self.db_path} already exists and is populated.")
            # Ensure analyzer tables exist even if database exists
            self.create_analyzer_tables()
