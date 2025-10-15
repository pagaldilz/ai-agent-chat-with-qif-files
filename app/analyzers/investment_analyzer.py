import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging
from app.parsers.investment_parser import InvestmentParser

class InvestmentAnalyzer:
    def __init__(self, engine, qif_dir: str):
        self.engine = engine
        self.qif_dir = qif_dir
        self.logger = logging.getLogger('investment_analyzer')
        
    def create_investments_table(self):
        """Create the investments table if it doesn't exist."""
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS investments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date DATE,
            security TEXT,
            action TEXT,
            quantity REAL,
            price REAL,
            commission REAL,
            amount REAL,
            memo TEXT,
            account_name TEXT,
            source_file TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        
        with self.engine.connect() as conn:
            conn.execute(create_table_sql)
            conn.commit()
    
    def parse_and_store_investments(self) -> Dict:
        """Parse investment data and store in database."""
        try:
            parser = InvestmentParser(self.qif_dir)
            df = parser.parse_investment_qif()
            
            if df.empty:
                return {'status': 'no_data', 'message': 'No investment data found'}
            
            # Create table
            self.create_investments_table()
            
            # Store in database
            with self.engine.connect() as conn:
                # Clear existing data
                conn.execute("DELETE FROM investments")
                
                # Insert new data
                df.to_sql('investments', conn, if_exists='append', index=False)
                conn.commit()
            
            # Generate analysis
            portfolio_summary = parser.get_portfolio_summary(df)
            transaction_summary = parser.get_transaction_summary(df)
            
            self.logger.info(f"Stored {len(df)} investment transactions")
            
            return {
                'status': 'success',
                'transactions_count': len(df),
                'portfolio_summary': portfolio_summary,
                'transaction_summary': transaction_summary
            }
            
        except Exception as e:
            self.logger.exception("Failed to parse and store investments")
            return {'status': 'error', 'message': str(e)}
    
    def get_portfolio_summary(self) -> Dict:
        """Get current portfolio summary from database."""
        query = """
        SELECT 
            security,
            SUM(quantity) as total_quantity,
            AVG(price) as avg_price,
            SUM(amount) as total_invested,
            COUNT(*) as transaction_count
        FROM investments 
        GROUP BY security
        HAVING total_quantity > 0
        ORDER BY total_invested DESC
        """
        
        try:
            df = pd.read_sql(query, self.engine)
            
            if df.empty:
                return {'holdings': [], 'total_value': 0, 'total_invested': 0}
            
            # Calculate current values (using average price as proxy for current price)
            df['current_value'] = df['total_quantity'] * df['avg_price']
            df['unrealized_gain_loss'] = df['current_value'] - df['total_invested']
            df['return_percentage'] = (df['unrealized_gain_loss'] / df['total_invested'] * 100).fillna(0)
            
            total_value = df['current_value'].sum()
            total_invested = df['total_invested'].sum()
            total_gain_loss = df['unrealized_gain_loss'].sum()
            overall_return = (total_gain_loss / total_invested * 100) if total_invested > 0 else 0
            
            return {
                'holdings': df.to_dict('records'),
                'total_value': round(total_value, 2),
                'total_invested': round(total_invested, 2),
                'total_gain_loss': round(total_gain_loss, 2),
                'overall_return': round(overall_return, 2),
                'holdings_count': len(df)
            }
            
        except Exception as e:
            self.logger.warning(f"Failed to get portfolio summary: {e}")
            return {'holdings': [], 'total_value': 0, 'total_invested': 0}
    
    def get_transaction_history(self, security: str = None, limit: int = 100) -> List[Dict]:
        """Get investment transaction history."""
        query = """
        SELECT * FROM investments 
        """
        params = []
        
        if security:
            query += " WHERE security = ?"
            params.append(security)
        
        query += " ORDER BY date DESC LIMIT ?"
        params.append(limit)
        
        try:
            df = pd.read_sql(query, self.engine, params=params)
            return df.to_dict('records')
        except Exception as e:
            self.logger.warning(f"Failed to get transaction history: {e}")
            return []
    
    def get_performance_analysis(self) -> Dict:
        """Analyze investment performance over time."""
        query = """
        SELECT 
            strftime('%Y-%m', date) as month,
            action,
            SUM(amount) as total_amount,
            SUM(quantity) as total_quantity,
            COUNT(*) as transaction_count
        FROM investments 
        GROUP BY strftime('%Y-%m', date), action
        ORDER BY month DESC
        """
        
        try:
            df = pd.read_sql(query, self.engine)
            
            if df.empty:
                return {'monthly_performance': [], 'action_breakdown': []}
            
            # Monthly performance
            monthly_performance = df.groupby('month').agg({
                'total_amount': 'sum',
                'transaction_count': 'sum'
            }).reset_index()
            
            # Action breakdown
            action_breakdown = df.groupby('action').agg({
                'total_amount': 'sum',
                'transaction_count': 'sum'
            }).reset_index()
            
            return {
                'monthly_performance': monthly_performance.to_dict('records'),
                'action_breakdown': action_breakdown.to_dict('records')
            }
            
        except Exception as e:
            self.logger.warning(f"Failed to get performance analysis: {e}")
            return {'monthly_performance': [], 'action_breakdown': []}
    
    def get_asset_allocation(self) -> Dict:
        """Get asset allocation breakdown."""
        query = """
        SELECT 
            security,
            SUM(quantity) as total_quantity,
            AVG(price) as avg_price,
            SUM(amount) as total_invested
        FROM investments 
        GROUP BY security
        HAVING total_quantity > 0
        """
        
        try:
            df = pd.read_sql(query, self.engine)
            
            if df.empty:
                return {'allocation': [], 'total_value': 0}
            
            # Calculate current values
            df['current_value'] = df['total_quantity'] * df['avg_price']
            total_value = df['current_value'].sum()
            
            # Calculate allocation percentages
            df['allocation_percentage'] = (df['current_value'] / total_value * 100).round(2)
            
            # Sort by allocation percentage
            df = df.sort_values('allocation_percentage', ascending=False)
            
            return {
                'allocation': df.to_dict('records'),
                'total_value': round(total_value, 2)
            }
            
        except Exception as e:
            self.logger.warning(f"Failed to get asset allocation: {e}")
            return {'allocation': [], 'total_value': 0}
