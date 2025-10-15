import os
import re
import pandas as pd
import logging
from sqlalchemy import create_engine, Column, Float, String, Date, MetaData, Table
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
            Column('date', Date),
            Column('payee', String),
            Column('category', String),
            Column('memo', String),
            Column('amount', Float),
        )

    def parse_qif_date(self, qif_date_str):
            """
            Parse QIF date like '4/11'2004' and return a Python date object in yyyy-mm-dd format.
            Logs and returns None if parsing fails.
            """
            try:
                # Handle mm/dd'yyyy format (with or without leading zero)
                if "'" in qif_date_str:
                    parts = qif_date_str.split("'")
                    if len(parts) == 2:
                        mmdd, yyyy = parts
                        month, day = [int(x) for x in mmdd.split('/')]
                        year = int(yyyy)
                        return date(year, month, day)
                # Fallback: try mm/dd/yyyy
                return datetime.strptime(qif_date_str, "%m/%d/%Y").date()
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
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        if line == '^':
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
