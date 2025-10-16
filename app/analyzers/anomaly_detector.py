import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
import logging
from scipy import stats

class AnomalyDetector:
    def __init__(self, engine):
        self.engine = engine
        self.logger = logging.getLogger('anomaly_detector')
        
    def detect_amount_anomalies(self, z_threshold: float = 2.5) -> List[Dict]:
        """Detect anomalous transaction amounts using Z-score method."""
        # Get all transactions with amounts
        query = """
        SELECT id, date, payee, amount, category, account_name
        FROM transactions 
        WHERE amount IS NOT NULL AND amount != 0
        ORDER BY date
        """
        
        df = pd.read_sql(query, self.engine)
        if df.empty:
            return []
        
        anomalies = []
        
        # Calculate Z-scores for amounts
        amounts = df['amount'].values
        z_scores = np.abs(stats.zscore(amounts))
        
        # Find anomalies
        anomaly_indices = np.where(z_scores > z_threshold)[0]
        
        for idx in anomaly_indices:
            row = df.iloc[idx]
            anomaly = {
                'transaction_id': row['id'],
                'anomaly_type': 'amount_outlier',
                'score': float(z_scores[idx]),
                'explanation': f"Transaction amount ${row['amount']:,.2f} is {z_scores[idx]:.1f} standard deviations from the mean",
                'date': row['date'],
                'payee': row['payee'],
                'amount': row['amount'],
                'category': row['category'],
                'account_name': row['account_name']
            }
            anomalies.append(anomaly)
        
        return anomalies
    
    def detect_frequency_anomalies(self, lookback_days: int = 30) -> List[Dict]:
        """Detect anomalous spending frequency patterns."""
        # Get recent transactions
        cutoff_date = datetime.now() - timedelta(days=lookback_days)
        
        query = """
        SELECT id, date, payee, amount, category, account_name
        FROM transactions 
        WHERE date >= ? AND amount < 0
        ORDER BY date
        """
        
        df = pd.read_sql(query, self.engine, params=(cutoff_date.isoformat(),))
        if df.empty:
            return []
        
        # Convert date column to datetime
        df['date'] = pd.to_datetime(df['date'])
        
        anomalies = []
        
        # Group by payee to find frequency anomalies
        for payee, group in df.groupby('payee'):
            if len(group) < 3:  # Need at least 3 transactions to detect frequency
                continue
            
            # Calculate time between transactions
            group = group.sort_values('date')
            time_diffs = group['date'].diff().dt.days.dropna()
            
            if len(time_diffs) == 0:
                continue
            
            # Calculate average time between transactions
            avg_interval = time_diffs.mean()
            std_interval = time_diffs.std()
            
            # Check for unusually frequent transactions
            recent_cutoff = datetime.now() - timedelta(days=7)
            # Ensure date column is datetime for comparison
            group['date'] = pd.to_datetime(group['date'])
            recent_transactions = group[group['date'] >= recent_cutoff]
            if len(recent_transactions) > 3:  # More than 3 transactions in a week
                anomaly = {
                    'transaction_id': recent_transactions.iloc[-1]['id'],
                    'anomaly_type': 'frequency_spike',
                    'score': len(recent_transactions) / 3.0,  # Normalize by expected frequency
                    'explanation': f"Unusually frequent transactions with {payee}: {len(recent_transactions)} transactions in the last 7 days",
                    'date': recent_transactions.iloc[-1]['date'],
                    'payee': payee,
                    'amount': recent_transactions.iloc[-1]['amount'],
                    'category': recent_transactions.iloc[-1]['category'],
                    'account_name': recent_transactions.iloc[-1]['account_name']
                }
                anomalies.append(anomaly)
        
        return anomalies
    
    def detect_new_merchant_anomalies(self, lookback_days: int = 90) -> List[Dict]:
        """Detect transactions with new merchants that might be suspicious."""
        # Get all merchants and their first appearance
        query = """
        SELECT payee, MIN(date) as first_seen, COUNT(*) as transaction_count
        FROM transactions 
        WHERE payee IS NOT NULL AND payee != ''
        GROUP BY payee
        """
        
        df = pd.read_sql(query, self.engine)
        if df.empty:
            return []
        
        # Find merchants that appeared recently
        cutoff_date = datetime.now() - timedelta(days=lookback_days)
        recent_merchants = df[df['first_seen'] >= cutoff_date]
        
        anomalies = []
        
        for _, merchant in recent_merchants.iterrows():
            # Get transactions for this merchant
            merchant_query = """
            SELECT id, date, payee, amount, category, account_name
            FROM transactions 
            WHERE payee = ?
            ORDER BY date
            """
            
            merchant_df = pd.read_sql(merchant_query, self.engine, params=(merchant['payee'],))
            
            # Calculate risk score based on amount and frequency
            total_amount = abs(merchant_df['amount'].sum())
            transaction_count = len(merchant_df)
            
            # Higher risk for larger amounts or many transactions
            risk_score = min(total_amount / 1000.0 + transaction_count / 10.0, 10.0)
            
            if risk_score > 2.0:  # Threshold for new merchant risk
                # Get the most recent transaction
                latest_transaction = merchant_df.iloc[-1]
                
                anomaly = {
                    'transaction_id': latest_transaction['id'],
                    'anomaly_type': 'new_merchant',
                    'score': risk_score,
                    'explanation': f"New merchant '{merchant['payee']}' with {transaction_count} transactions totaling ${total_amount:,.2f}",
                    'date': latest_transaction['date'],
                    'payee': merchant['payee'],
                    'amount': latest_transaction['amount'],
                    'category': latest_transaction['category'],
                    'account_name': latest_transaction['account_name']
                }
                anomalies.append(anomaly)
        
        return anomalies
    
    def detect_all_anomalies(self) -> List[Dict]:
        """Detect all types of anomalies."""
        all_anomalies = []
        
        # Amount anomalies
        amount_anomalies = self.detect_amount_anomalies()
        all_anomalies.extend(amount_anomalies)
        
        # Frequency anomalies
        frequency_anomalies = self.detect_frequency_anomalies()
        all_anomalies.extend(frequency_anomalies)
        
        # New merchant anomalies
        new_merchant_anomalies = self.detect_new_merchant_anomalies()
        all_anomalies.extend(new_merchant_anomalies)
        
        # Sort by score (highest risk first)
        all_anomalies.sort(key=lambda x: x['score'], reverse=True)
        
        self.logger.info(f"Detected {len(all_anomalies)} anomalies")
        return all_anomalies
    
    def save_anomalies(self, anomalies: List[Dict]):
        """Save anomalies to the database."""
        if not anomalies:
            return
        
        # Create anomalies table if it doesn't exist
        create_table_sql = """
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
            conn.execute(create_table_sql)
            conn.commit()
            
            # Clear existing anomalies
            conn.execute("DELETE FROM anomalies")
            
            # Insert new anomalies
            for anomaly in anomalies:
                insert_sql = """
                INSERT INTO anomalies 
                (transaction_id, anomaly_type, score, explanation, date, payee, amount, category, account_name)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                conn.execute(insert_sql, (
                    anomaly['transaction_id'],
                    anomaly['anomaly_type'],
                    anomaly['score'],
                    anomaly['explanation'],
                    anomaly['date'],
                    anomaly['payee'],
                    anomaly['amount'],
                    anomaly['category'],
                    anomaly['account_name']
                ))
            
            conn.commit()
            self.logger.info(f"Saved {len(anomalies)} anomalies to database")
    
    def get_anomalies(self, anomaly_type: str = None, limit: int = 50) -> List[Dict]:
        """Retrieve anomalies from the database."""
        query = """
        SELECT * FROM anomalies 
        """
        
        params = []
        if anomaly_type:
            query += " WHERE anomaly_type = ?"
            params.append(anomaly_type)
        
        query += " ORDER BY score DESC LIMIT ?"
        params.append(limit)
        
        try:
            df = pd.read_sql(query, self.engine, params=params)
            return df.to_dict('records')
        except Exception as e:
            self.logger.warning(f"Failed to get anomalies: {e}")
            return []
    
    def get_anomaly_summary(self) -> Dict:
        """Get summary statistics about anomalies."""
        query = """
        SELECT 
            anomaly_type,
            COUNT(*) as count,
            AVG(score) as avg_score,
            MAX(score) as max_score
        FROM anomalies 
        GROUP BY anomaly_type
        """
        
        try:
            df = pd.read_sql(query, self.engine)
            summary = {}
            for _, row in df.iterrows():
                summary[row['anomaly_type']] = {
                    'count': row['count'],
                    'avg_score': round(row['avg_score'], 2),
                    'max_score': round(row['max_score'], 2)
                }
            return summary
        except Exception as e:
            self.logger.warning(f"Failed to get anomaly summary: {e}")
            return {}
