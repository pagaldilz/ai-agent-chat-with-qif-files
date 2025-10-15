import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
import logging
from collections import defaultdict

class TransferDetector:
    def __init__(self, engine):
        self.engine = engine
        self.logger = logging.getLogger('transfer_detector')
        
    def detect_transfers(self, tolerance_days: int = 3, tolerance_amount: float = 0.01) -> List[Dict]:
        """
        Detect transfers between accounts by matching amounts and dates.
        
        Args:
            tolerance_days: Maximum days between matching transactions
            tolerance_amount: Maximum amount difference for matching (in dollars)
        """
        # Get all transactions
        query = """
        SELECT id, date, payee, amount, account_name, account_type, memo
        FROM transactions 
        WHERE account_name IS NOT NULL AND account_name != ''
        ORDER BY date, account_name
        """
        
        df = pd.read_sql(query, self.engine)
        if df.empty:
            return []
        
        # Convert date column to datetime
        df['date'] = pd.to_datetime(df['date'])
        
        transfers = []
        processed_ids = set()
        
        # Group by account to find potential transfers
        for account, account_transactions in df.groupby('account_name'):
            for _, transaction in account_transactions.iterrows():
                if transaction['id'] in processed_ids:
                    continue
                
                # Look for matching transactions in other accounts
                amount = transaction['amount']
                date = transaction['date']
                
                # Find potential matches in other accounts
                potential_matches = df[
                    (df['account_name'] != account) &
                    (df['id'] != transaction['id']) &
                    (df['id'].isin(processed_ids) == False) &
                    (abs(df['amount'] + amount) <= tolerance_amount) &  # Opposite sign, similar amount
                    (abs((df['date'] - date).dt.days) <= tolerance_days)  # Within date tolerance
                ]
                
                if not potential_matches.empty:
                    # Find the best match (closest date and amount)
                    potential_matches['date_diff'] = abs((potential_matches['date'] - date).dt.days)
                    potential_matches['amount_diff'] = abs(potential_matches['amount'] + amount)
                    
                    # Score matches (lower is better)
                    potential_matches['score'] = (
                        potential_matches['date_diff'] * 0.7 + 
                        potential_matches['amount_diff'] * 0.3
                    )
                    
                    best_match = potential_matches.loc[potential_matches['score'].idxmin()]
                    
                    # Create transfer record
                    transfer = {
                        'from_transaction_id': transaction['id'] if amount < 0 else best_match['id'],
                        'to_transaction_id': best_match['id'] if amount < 0 else transaction['id'],
                        'from_account': account if amount < 0 else best_match['account_name'],
                        'to_account': best_match['account_name'] if amount < 0 else account,
                        'amount': abs(amount),
                        'transfer_date': date.isoformat(),
                        'confidence_score': 1.0 - (best_match['score'] / 10.0),  # Normalize score
                        'detection_method': 'amount_date_matching'
                    }
                    
                    transfers.append(transfer)
                    
                    # Mark both transactions as processed
                    processed_ids.add(transaction['id'])
                    processed_ids.add(best_match['id'])
        
        # Sort by confidence score
        transfers.sort(key=lambda x: x['confidence_score'], reverse=True)
        
        self.logger.info(f"Detected {len(transfers)} potential transfers")
        return transfers
    
    def save_transfers(self, transfers: List[Dict]):
        """Save detected transfers to the database."""
        if not transfers:
            return
        
        # Create transfers table if it doesn't exist
        create_table_sql = """
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
        
        with self.engine.connect() as conn:
            conn.execute(create_table_sql)
            conn.commit()
            
            # Clear existing transfers
            conn.execute("DELETE FROM transfers")
            
            # Insert new transfers
            for transfer in transfers:
                insert_sql = """
                INSERT INTO transfers 
                (from_transaction_id, to_transaction_id, from_account, to_account, 
                 amount, transfer_date, confidence_score, detection_method)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """
                conn.execute(insert_sql, (
                    transfer['from_transaction_id'],
                    transfer['to_transaction_id'],
                    transfer['from_account'],
                    transfer['to_account'],
                    transfer['amount'],
                    transfer['transfer_date'],
                    transfer['confidence_score'],
                    transfer['detection_method']
                ))
            
            conn.commit()
            self.logger.info(f"Saved {len(transfers)} transfers to database")
    
    def get_transfers(self, limit: int = 100) -> List[Dict]:
        """Retrieve transfers from the database."""
        query = """
        SELECT t.*, 
               t1.date as from_date, t1.payee as from_payee, t1.memo as from_memo,
               t2.date as to_date, t2.payee as to_payee, t2.memo as to_memo
        FROM transfers t
        LEFT JOIN transactions t1 ON t.from_transaction_id = t1.id
        LEFT JOIN transactions t2 ON t.to_transaction_id = t2.id
        ORDER BY t.confidence_score DESC
        LIMIT ?
        """
        
        try:
            df = pd.read_sql(query, self.engine, params=[limit])
            return df.to_dict('records')
        except Exception as e:
            self.logger.warning(f"Failed to get transfers: {e}")
            return []
    
    def calculate_net_cash_flow(self, account_name: str = None, exclude_transfers: bool = True) -> Dict:
        """Calculate net cash flow excluding transfers."""
        query = """
        SELECT 
            SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as total_income,
            SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) as total_expenses,
            COUNT(*) as transaction_count
        FROM transactions 
        WHERE 1=1
        """
        params = []
        
        if account_name:
            query += " AND account_name = ?"
            params.append(account_name)
        
        if exclude_transfers:
            # Exclude transactions that are part of transfers
            query += """
            AND id NOT IN (
                SELECT from_transaction_id FROM transfers
                UNION
                SELECT to_transaction_id FROM transfers
            )
            """
        
        try:
            df = pd.read_sql(query, self.engine, params=params)
            if not df.empty:
                row = df.iloc[0]
                net_cash_flow = row['total_income'] - row['total_expenses']
                
                return {
                    'total_income': round(row['total_income'], 2),
                    'total_expenses': round(row['total_expenses'], 2),
                    'net_cash_flow': round(net_cash_flow, 2),
                    'transaction_count': row['transaction_count'],
                    'excludes_transfers': exclude_transfers
                }
        except Exception as e:
            self.logger.warning(f"Failed to calculate net cash flow: {e}")
        
        return {'total_income': 0, 'total_expenses': 0, 'net_cash_flow': 0, 'transaction_count': 0}
    
    def get_transfer_summary(self) -> Dict:
        """Get summary statistics about transfers."""
        query = """
        SELECT 
            COUNT(*) as total_transfers,
            SUM(amount) as total_transfer_amount,
            AVG(confidence_score) as avg_confidence,
            COUNT(DISTINCT from_account) as unique_from_accounts,
            COUNT(DISTINCT to_account) as unique_to_accounts
        FROM transfers
        """
        
        try:
            df = pd.read_sql(query, self.engine)
            if not df.empty:
                row = df.iloc[0]
                return {
                    'total_transfers': row['total_transfers'],
                    'total_transfer_amount': round(row['total_transfer_amount'], 2),
                    'avg_confidence': round(row['avg_confidence'], 3),
                    'unique_from_accounts': row['unique_from_accounts'],
                    'unique_to_accounts': row['unique_to_accounts']
                }
        except Exception as e:
            self.logger.warning(f"Failed to get transfer summary: {e}")
        
        return {'total_transfers': 0, 'total_transfer_amount': 0, 'avg_confidence': 0}
    
    def update_transaction_transfer_flags(self):
        """Update transactions table with is_transfer flags."""
        # Add is_transfer column if it doesn't exist
        alter_sql = """
        ALTER TABLE transactions ADD COLUMN is_transfer BOOLEAN DEFAULT 0
        """
        
        try:
            with self.engine.connect() as conn:
                # Try to add the column (will fail if it already exists)
                try:
                    conn.execute(alter_sql)
                    conn.commit()
                except Exception:
                    pass  # Column already exists
                
                # Update is_transfer flags
                update_sql = """
                UPDATE transactions 
                SET is_transfer = 1 
                WHERE id IN (
                    SELECT from_transaction_id FROM transfers
                    UNION
                    SELECT to_transaction_id FROM transfers
                )
                """
                conn.execute(update_sql)
                conn.commit()
                
                self.logger.info("Updated transaction transfer flags")
        except Exception as e:
            self.logger.warning(f"Failed to update transfer flags: {e}")
