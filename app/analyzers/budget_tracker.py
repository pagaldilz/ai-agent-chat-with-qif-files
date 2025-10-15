import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging

class BudgetTracker:
    def __init__(self, engine):
        self.engine = engine
        self.logger = logging.getLogger('budget_tracker')
        
    def create_budget_tables(self):
        """Create budgets and goals tables if they don't exist."""
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
        
        with self.engine.connect() as conn:
            conn.execute(budgets_sql)
            conn.execute(goals_sql)
            conn.commit()
    
    def get_spending_by_category(self, start_date: str = None, end_date: str = None) -> Dict:
        """Get spending breakdown by category for budget analysis."""
        query = """
        SELECT 
            category,
            COUNT(*) as transaction_count,
            SUM(ABS(amount)) as total_spent,
            AVG(ABS(amount)) as avg_transaction
        FROM transactions 
        WHERE amount < 0 AND category IS NOT NULL AND category != ''
        """
        params = []
        
        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)
        
        query += " GROUP BY category ORDER BY total_spent DESC"
        
        try:
            df = pd.read_sql(query, self.engine, params=params)
            return df.to_dict('records')
        except Exception as e:
            self.logger.warning(f"Failed to get spending by category: {e}")
            return []
    
    def suggest_budgets(self, period: str = 'monthly') -> List[Dict]:
        """Generate budget suggestions based on historical spending."""
        # Get spending data for the last 3 months for analysis
        end_date = datetime.now()
        if period == 'monthly':
            start_date = end_date - timedelta(days=90)
        elif period == 'weekly':
            start_date = end_date - timedelta(days=30)
        else:
            start_date = end_date - timedelta(days=365)
        
        spending_data = self.get_spending_by_category(
            start_date.isoformat(), 
            end_date.isoformat()
        )
        
        suggestions = []
        for category_data in spending_data:
            category = category_data['category']
            avg_spent = category_data['total_spent']
            transaction_count = category_data['transaction_count']
            
            # Calculate suggested budget (average spending + 10% buffer)
            suggested_amount = avg_spent * 1.1
            
            # Only suggest budgets for categories with significant spending
            if avg_spent > 50 and transaction_count >= 3:
                suggestions.append({
                    'category': category,
                    'suggested_amount': round(suggested_amount, 2),
                    'historical_average': round(avg_spent, 2),
                    'transaction_count': transaction_count,
                    'confidence': min(transaction_count / 10.0, 1.0)  # Higher confidence with more data
                })
        
        # Sort by suggested amount
        suggestions.sort(key=lambda x: x['suggested_amount'], reverse=True)
        return suggestions
    
    def create_budget(self, category: str, amount: float, period: str, 
                     start_date: str = None, end_date: str = None) -> Dict:
        """Create a new budget."""
        if not start_date:
            start_date = datetime.now().isoformat()
        
        if not end_date and period == 'monthly':
            end_date = (datetime.now() + timedelta(days=30)).isoformat()
        elif not end_date and period == 'weekly':
            end_date = (datetime.now() + timedelta(days=7)).isoformat()
        
        try:
            with self.engine.connect() as conn:
                insert_sql = """
                INSERT INTO budgets (category, period, amount, start_date, end_date)
                VALUES (?, ?, ?, ?, ?)
                """
                conn.execute(insert_sql, (category, period, amount, start_date, end_date))
                conn.commit()
                
                return {'status': 'success', 'message': f'Budget created for {category}'}
        except Exception as e:
            self.logger.error(f"Failed to create budget: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def get_budgets(self) -> List[Dict]:
        """Get all budgets."""
        query = """
        SELECT * FROM budgets 
        ORDER BY created_at DESC
        """
        
        try:
            df = pd.read_sql(query, self.engine)
            return df.to_dict('records')
        except Exception as e:
            self.logger.warning(f"Failed to get budgets: {e}")
            return []
    
    def get_budget_progress(self) -> List[Dict]:
        """Get budget progress with actual vs planned spending."""
        budgets = self.get_budgets()
        progress = []
        
        for budget in budgets:
            category = budget['category']
            budget_amount = budget['amount']
            start_date = budget['start_date']
            end_date = budget['end_date']
            
            # Get actual spending for this category and period
            query = """
            SELECT SUM(ABS(amount)) as actual_spent
            FROM transactions 
            WHERE category = ? AND amount < 0 AND date >= ? AND date <= ?
            """
            
            try:
                df = pd.read_sql(query, self.engine, params=[category, start_date, end_date])
                actual_spent = df.iloc[0]['actual_spent'] if not df.empty else 0
                
                # Calculate progress
                progress_percentage = (actual_spent / budget_amount * 100) if budget_amount > 0 else 0
                remaining = max(0, budget_amount - actual_spent)
                over_budget = actual_spent > budget_amount
                
                progress.append({
                    'budget_id': budget['id'],
                    'category': category,
                    'budget_amount': budget_amount,
                    'actual_spent': round(actual_spent, 2),
                    'remaining': round(remaining, 2),
                    'progress_percentage': round(progress_percentage, 1),
                    'over_budget': over_budget,
                    'period': budget['period'],
                    'start_date': start_date,
                    'end_date': end_date
                })
            except Exception as e:
                self.logger.warning(f"Failed to get progress for budget {category}: {e}")
        
        return progress
    
    def create_goal(self, name: str, target_amount: float, deadline: str = None, 
                   category: str = None) -> Dict:
        """Create a new financial goal."""
        try:
            with self.engine.connect() as conn:
                insert_sql = """
                INSERT INTO goals (name, target_amount, deadline, category)
                VALUES (?, ?, ?, ?)
                """
                conn.execute(insert_sql, (name, target_amount, deadline, category))
                conn.commit()
                
                return {'status': 'success', 'message': f'Goal created: {name}'}
        except Exception as e:
            self.logger.error(f"Failed to create goal: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def get_goals(self) -> List[Dict]:
        """Get all goals."""
        query = """
        SELECT * FROM goals 
        ORDER BY created_at DESC
        """
        
        try:
            df = pd.read_sql(query, self.engine)
            return df.to_dict('records')
        except Exception as e:
            self.logger.warning(f"Failed to get goals: {e}")
            return []
    
    def update_goal_progress(self, goal_id: int, current_amount: float) -> Dict:
        """Update the current amount for a goal."""
        try:
            with self.engine.connect() as conn:
                update_sql = "UPDATE goals SET current_amount = ? WHERE id = ?"
                conn.execute(update_sql, (current_amount, goal_id))
                conn.commit()
                
                return {'status': 'success', 'message': 'Goal progress updated'}
        except Exception as e:
            self.logger.error(f"Failed to update goal progress: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def get_goal_progress(self) -> List[Dict]:
        """Get goal progress with completion percentages."""
        goals = self.get_goals()
        progress = []
        
        for goal in goals:
            target_amount = goal['target_amount']
            current_amount = goal['current_amount']
            
            # Calculate progress
            progress_percentage = (current_amount / target_amount * 100) if target_amount > 0 else 0
            remaining = max(0, target_amount - current_amount)
            is_complete = current_amount >= target_amount
            
            # Calculate days remaining if deadline is set
            days_remaining = None
            if goal['deadline']:
                try:
                    deadline = datetime.fromisoformat(goal['deadline'])
                    days_remaining = (deadline - datetime.now()).days
                except Exception:
                    pass
            
            progress.append({
                'goal_id': goal['id'],
                'name': goal['name'],
                'target_amount': target_amount,
                'current_amount': current_amount,
                'remaining': round(remaining, 2),
                'progress_percentage': round(progress_percentage, 1),
                'is_complete': is_complete,
                'deadline': goal['deadline'],
                'days_remaining': days_remaining,
                'category': goal['category']
            })
        
        return progress
    
    def get_budget_summary(self) -> Dict:
        """Get overall budget summary."""
        budgets = self.get_budgets()
        goals = self.get_goals()
        
        total_budget_amount = sum(budget['amount'] for budget in budgets)
        total_goal_amount = sum(goal['target_amount'] for goal in goals)
        total_goal_progress = sum(goal['current_amount'] for goal in goals)
        
        return {
            'total_budgets': len(budgets),
            'total_budget_amount': round(total_budget_amount, 2),
            'total_goals': len(goals),
            'total_goal_amount': round(total_goal_amount, 2),
            'total_goal_progress': round(total_goal_progress, 2),
            'goal_completion_rate': round((total_goal_progress / total_goal_amount * 100), 1) if total_goal_amount > 0 else 0
        }
