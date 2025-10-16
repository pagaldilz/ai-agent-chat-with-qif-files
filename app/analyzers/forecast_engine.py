import pandas as pd
import numpy as np
from datetime import datetime, timedelta, date
from typing import List, Dict, Tuple, Optional
import logging
from collections import defaultdict

class ForecastEngine:
    def __init__(self, engine):
        self.engine = engine
        self.logger = logging.getLogger('forecast_engine')
        
    def get_historical_balance(self, account_name: str = None, days_back: int = 90) -> float:
        """Get the current balance for an account based on historical transactions."""
        cutoff_date = datetime.now() - timedelta(days=days_back)
        
        query = """
        SELECT SUM(amount) as balance
        FROM transactions 
        WHERE date >= ?
        """
        params = [cutoff_date.isoformat()]
        
        if account_name:
            query += " AND account_name = ?"
            params.append(account_name)
        
        try:
            result = pd.read_sql(query, self.engine, params=params)
            return float(result.iloc[0]['balance']) if result.iloc[0]['balance'] is not None else 0.0
        except Exception as e:
            self.logger.warning(f"Failed to get historical balance: {e}")
            return 0.0
    
    def get_recurring_transactions(self) -> List[Dict]:
        """Get recurring transaction patterns for forecasting."""
        query = """
        SELECT * FROM recurring_transactions 
        WHERE confidence_score > 0.5
        ORDER BY confidence_score DESC
        """
        
        try:
            df = pd.read_sql(query, self.engine)
            return df.to_dict('records')
        except Exception as e:
            self.logger.warning(f"Failed to get recurring transactions: {e}")
            return []
    
    def get_upcoming_bills(self, days_ahead: int = 30) -> List[Dict]:
        """Get upcoming bills based on recurring patterns."""
        recurring = self.get_recurring_transactions()
        upcoming_bills = []
        
        for pattern in recurring:
            # Guard against missing/invalid ISO strings
            last_seen = None
            next_expected = None
            try:
                if pattern.get('last_seen'):
                    last_seen = datetime.fromisoformat(str(pattern['last_seen']))
            except Exception:
                last_seen = None
            try:
                if pattern.get('next_expected'):
                    next_expected = datetime.fromisoformat(str(pattern['next_expected']))
            except Exception:
                next_expected = None
            
            # Check if the next expected date is within our forecast period
            if next_expected is not None and next_expected <= datetime.now() + timedelta(days=days_ahead):
                upcoming_bills.append({
                    'merchant': pattern['merchant_pattern'],
                    'amount': pattern['amount_avg'],
                    'due_date': next_expected.isoformat(),
                    'frequency': pattern['frequency_category'],
                    'confidence': pattern['confidence_score'],
                    'category': pattern['category']
                })
        
        # Sort by due date
        upcoming_bills.sort(key=lambda x: x['due_date'])
        return upcoming_bills
    
    def calculate_monthly_income(self, account_name: str = None) -> float:
        """Calculate average monthly income from historical data."""
        query = """
        SELECT AVG(monthly_total) as avg_monthly_income
        FROM (
            SELECT strftime('%Y-%m', date) as month, SUM(amount) as monthly_total
            FROM transactions 
            WHERE amount > 0
        """
        params = []
        
        if account_name:
            query += " AND account_name = ?"
            params.append(account_name)
        
        query += """
            GROUP BY strftime('%Y-%m', date)
            HAVING monthly_total > 0
        ) monthly_income
        """
        
        try:
            result = pd.read_sql(query, self.engine, params=params)
            return float(result.iloc[0]['avg_monthly_income']) if result.iloc[0]['avg_monthly_income'] is not None else 0.0
        except Exception as e:
            self.logger.warning(f"Failed to calculate monthly income: {e}")
            return 0.0
    
    def calculate_monthly_expenses(self, account_name: str = None) -> float:
        """Calculate average monthly expenses from historical data."""
        query = """
        SELECT AVG(monthly_total) as avg_monthly_expenses
        FROM (
            SELECT strftime('%Y-%m', date) as month, ABS(SUM(amount)) as monthly_total
            FROM transactions 
            WHERE amount < 0
        """
        params = []
        
        if account_name:
            query += " AND account_name = ?"
            params.append(account_name)
        
        query += """
            GROUP BY strftime('%Y-%m', date)
            HAVING monthly_total > 0
        ) monthly_expenses
        """
        
        try:
            result = pd.read_sql(query, self.engine, params=params)
            return float(result.iloc[0]['avg_monthly_expenses']) if result.iloc[0]['avg_monthly_expenses'] is not None else 0.0
        except Exception as e:
            self.logger.warning(f"Failed to calculate monthly expenses: {e}")
            return 0.0
    
    def generate_forecast(self, days: int = 30, account_name: str = None) -> Dict:
        """Generate cash flow forecast for the specified number of days."""
        # Get current balance
        current_balance = self.get_historical_balance(account_name)
        
        # Get recurring patterns
        recurring = self.get_recurring_transactions()
        
        # Calculate average monthly income and expenses
        monthly_income = self.calculate_monthly_income(account_name)
        monthly_expenses = self.calculate_monthly_expenses(account_name)
        
        # Get upcoming bills
        upcoming_bills = self.get_upcoming_bills(days)
        
        # Calculate projected expenses for the forecast period
        projected_expenses = 0.0
        for bill in upcoming_bills:
            projected_expenses += bill['amount']
        
        # Add estimated expenses based on historical patterns
        daily_expense_rate = monthly_expenses / 30.0
        estimated_expenses = daily_expense_rate * days
        projected_expenses += estimated_expenses
        
        # Calculate projected income for the forecast period
        daily_income_rate = monthly_income / 30.0
        projected_income = daily_income_rate * days
        
        # Calculate projected balance
        projected_balance = current_balance + projected_income - projected_expenses
        
        # Calculate safe-to-spend amount (conservative estimate)
        safe_to_spend = max(0, projected_balance - (monthly_expenses * 0.5))  # Keep 50% of monthly expenses as buffer
        
        # Generate daily forecast
        daily_forecast = self._generate_daily_forecast(days, current_balance, daily_income_rate, daily_expense_rate, upcoming_bills)
        
        return {
            'forecast_period_days': days,
            'current_balance': round(current_balance, 2),
            'projected_balance': round(projected_balance, 2),
            'projected_income': round(projected_income, 2),
            'projected_expenses': round(projected_expenses, 2),
            'safe_to_spend': round(safe_to_spend, 2),
            'upcoming_bills': upcoming_bills,
            'daily_forecast': daily_forecast,
            'account_name': account_name,
            'generated_at': datetime.now().isoformat()
        }
    
    def _generate_daily_forecast(self, days: int, starting_balance: float, 
                               daily_income: float, daily_expenses: float, 
                               upcoming_bills: List[Dict]) -> List[Dict]:
        """Generate day-by-day forecast."""
        daily_forecast = []
        current_balance = starting_balance
        bill_index = 0
        
        for day in range(days):
            forecast_date = datetime.now() + timedelta(days=day)
            date_str = forecast_date.isoformat()
            
            # Add daily income and expenses
            daily_net = daily_income - daily_expenses
            current_balance += daily_net
            
            # Check for upcoming bills on this day
            bill_amount = 0.0
            bills_today = []
            
            while (bill_index < len(upcoming_bills) and 
                   datetime.fromisoformat(upcoming_bills[bill_index]['due_date']).date() == forecast_date.date()):
                bill = upcoming_bills[bill_index]
                bill_amount += bill['amount']
                bills_today.append(bill)
                current_balance -= bill['amount']
                bill_index += 1
            
            daily_forecast.append({
                'date': date_str,
                'projected_balance': round(current_balance, 2),
                'daily_income': round(daily_income, 2),
                'daily_expenses': round(daily_expenses, 2),
                'bills_due': round(bill_amount, 2),
                'bills_count': len(bills_today),
                'net_change': round(daily_net - bill_amount, 2)
            })
        
        return daily_forecast
    
    def get_forecast_summary(self, days: int = 30) -> Dict:
        """Get a summary of forecast data for multiple accounts."""
        # Get all unique accounts
        query = "SELECT DISTINCT account_name FROM transactions WHERE account_name IS NOT NULL"
        
        try:
            df = pd.read_sql(query, self.engine)
            accounts = df['account_name'].tolist()
        except Exception as e:
            self.logger.warning(f"Failed to get accounts: {e}")
            accounts = []
        
        # Generate forecast for each account
        account_forecasts = {}
        for account in accounts:
            forecast = self.generate_forecast(days, account)
            account_forecasts[account] = forecast
        
        # Generate overall forecast (all accounts combined)
        overall_forecast = self.generate_forecast(days, None)
        
        return {
            'overall_forecast': overall_forecast,
            'account_forecasts': account_forecasts,
            'total_accounts': len(accounts)
        }
    
    def get_spending_trends(self, days_back: int = 90) -> Dict:
        """Analyze spending trends to improve forecast accuracy."""
        cutoff_date = datetime.now() - timedelta(days=days_back)
        
        query = """
        SELECT 
            strftime('%Y-%m', date) as month,
            SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as income,
            SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) as expenses,
            COUNT(*) as transaction_count
        FROM transactions 
        WHERE date >= ?
        GROUP BY strftime('%Y-%m', date)
        ORDER BY month
        """
        
        try:
            df = pd.read_sql(query, self.engine, params=[cutoff_date.isoformat()])
            
            if df.empty:
                return {'trends': [], 'avg_monthly_income': 0, 'avg_monthly_expenses': 0}
            
            trends = df.to_dict('records')
            avg_monthly_income = df['income'].mean()
            avg_monthly_expenses = df['expenses'].mean()
            
            return {
                'trends': trends,
                'avg_monthly_income': round(avg_monthly_income, 2),
                'avg_monthly_expenses': round(avg_monthly_expenses, 2),
                'months_analyzed': len(trends)
            }
        except Exception as e:
            self.logger.warning(f"Failed to get spending trends: {e}")
            return {'trends': [], 'avg_monthly_income': 0, 'avg_monthly_expenses': 0}
