import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict
from typing import List, Dict, Tuple
import logging
from sqlalchemy import text

class RecurringDetector:
    def __init__(self, engine):
        self.engine = engine
        self.logger = logging.getLogger('recurring_detector')
        
    def detect_recurring_patterns(self) -> List[Dict]:
        """
        Detect recurring transaction patterns from the database.
        Returns a list of recurring transaction patterns with metadata.
        """
        # Get all transactions
        query = """
        SELECT date, payee, amount, category, account_name, account_type
        FROM transactions 
        WHERE payee IS NOT NULL AND payee != '' 
        AND amount IS NOT NULL
        ORDER BY date
        """
        
        df = pd.read_sql(query, self.engine)
        if df.empty:
            return []
            
        # Convert date column to datetime
        df['date'] = pd.to_datetime(df['date'])
        
        patterns = []
        
        # Group by payee to find recurring patterns
        for payee, group in df.groupby('payee'):
            if len(group) < 2:  # Need at least 2 transactions to be recurring
                continue
                
            # Sort by date
            group = group.sort_values('date')
            
            # Calculate time differences between transactions
            time_diffs = group['date'].diff().dt.days.dropna()
            
            if len(time_diffs) == 0:
                continue
                
            # Calculate average time between transactions
            avg_interval = time_diffs.mean()
            std_interval = time_diffs.std()
            
            # Calculate amount statistics
            amounts = group['amount'].values
            avg_amount = np.mean(amounts)
            std_amount = np.std(amounts)
            
            # Calculate confidence score based on consistency
            # Higher score for more consistent intervals and amounts
            interval_consistency = 1 - (std_interval / avg_interval) if avg_interval > 0 else 0
            amount_consistency = 1 - (std_amount / abs(avg_amount)) if avg_amount != 0 else 0
            
            confidence = (interval_consistency + amount_consistency) / 2
            
            # Only consider patterns with reasonable confidence and frequency
            if confidence > 0.3 and avg_interval > 0:
                # Determine frequency category
                if avg_interval <= 7:
                    frequency = "weekly"
                elif avg_interval <= 31:
                    frequency = "monthly"
                elif avg_interval <= 93:
                    frequency = "quarterly"
                else:
                    frequency = "yearly"
                
                # Get most recent transaction
                last_transaction = group.iloc[-1]
                # Ensure datetime and guard against NaT
                last_dt = pd.to_datetime(last_transaction['date'], errors='coerce')
                # Calculate next expected date safely
                next_expected = (last_dt + timedelta(days=int(avg_interval))) if pd.notna(last_dt) else None
                
                pattern = {
                    'merchant_pattern': payee,
                    'amount_avg': round(avg_amount, 2),
                    'amount_std': round(std_amount, 2),
                    'frequency_days': round(avg_interval, 1),
                    'frequency_category': frequency,
                    'last_seen': last_dt.isoformat() if pd.notna(last_dt) else None,
                    'next_expected': next_expected.isoformat() if isinstance(next_expected, pd.Timestamp) or hasattr(next_expected, 'isoformat') else (next_expected if next_expected is None else str(next_expected)),
                    'confidence_score': round(confidence, 3),
                    'transaction_count': len(group),
                    'category': last_transaction['category'],
                    'account_name': last_transaction['account_name'],
                    'account_type': last_transaction['account_type']
                }
                
                patterns.append(pattern)
        
        # Sort by confidence score
        patterns.sort(key=lambda x: x['confidence_score'], reverse=True)
        
        self.logger.info(f"Detected {len(patterns)} recurring patterns")
        return patterns
    
    def save_recurring_patterns(self, patterns: List[Dict]):
        """Save recurring patterns to the database."""
        if not patterns:
            return
            
        # Create recurring_transactions table if it doesn't exist
        create_table_sql = """
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
        
        with self.engine.connect() as conn:
            conn.execute(text(create_table_sql))
            conn.commit()
            
            # Clear existing patterns
            conn.execute(text("DELETE FROM recurring_transactions"))
            
            # Insert new patterns
            insert_sql = """
            INSERT INTO recurring_transactions 
            (merchant_pattern, amount_avg, amount_std, frequency_days, frequency_category,
             last_seen, next_expected, confidence_score, transaction_count, category,
             account_name, account_type)
            VALUES (:merchant_pattern, :amount_avg, :amount_std, :frequency_days, :frequency_category,
                    :last_seen, :next_expected, :confidence_score, :transaction_count, :category,
                    :account_name, :account_type)
            """
            for pattern in patterns:
                params = {
                    'merchant_pattern': pattern['merchant_pattern'],
                    'amount_avg': pattern['amount_avg'],
                    'amount_std': pattern['amount_std'],
                    'frequency_days': pattern['frequency_days'],
                    'frequency_category': pattern['frequency_category'],
                    'last_seen': pattern['last_seen'],
                    'next_expected': pattern['next_expected'],
                    'confidence_score': pattern['confidence_score'],
                    'transaction_count': pattern['transaction_count'],
                    'category': pattern['category'],
                    'account_name': pattern['account_name'],
                    'account_type': pattern['account_type'],
                }
                conn.execute(text(insert_sql), params)
            
            conn.commit()
            self.logger.info(f"Saved {len(patterns)} recurring patterns to database")
    
    def get_recurring_patterns(self) -> List[Dict]:
        """Retrieve recurring patterns from the database."""
        try:
            query = """
            SELECT * FROM recurring_transactions 
            ORDER BY confidence_score DESC
            """
            
            df = pd.read_sql(query, self.engine)
            if df.empty:
                return []
            
            # Convert DataFrame to list of dictionaries, handling NaN values
            records = []
            for _, row in df.iterrows():
                record = {}
                for col in df.columns:
                    value = row[col]
                    if pd.isna(value):
                        record[col] = None
                    else:
                        record[col] = value
                records.append(record)
            return records
        except Exception as e:
            self.logger.warning(f"Failed to get recurring patterns: {e}")
            return []
    
    def calculate_monthly_projections(self, patterns: List[Dict]) -> Dict:
        """Calculate monthly spending projections based on recurring patterns."""
        monthly_total = 0
        weekly_total = 0
        quarterly_total = 0
        yearly_total = 0
        
        for pattern in patterns:
            amount = pattern['amount_avg']
            frequency = pattern['frequency_category']
            
            if frequency == 'weekly':
                monthly_total += amount * 4.33  # Average weeks per month
                weekly_total += amount
            elif frequency == 'monthly':
                monthly_total += amount
            elif frequency == 'quarterly':
                monthly_total += amount / 3
                quarterly_total += amount
            elif frequency == 'yearly':
                monthly_total += amount / 12
                yearly_total += amount
        
        return {
            'monthly_projection': round(monthly_total, 2),
            'weekly_projection': round(weekly_total, 2),
            'quarterly_projection': round(quarterly_total, 2),
            'yearly_projection': round(yearly_total, 2),
            'pattern_count': len(patterns)
        }
