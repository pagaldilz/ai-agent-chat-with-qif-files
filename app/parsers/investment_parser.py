import os
import re
import pandas as pd
import logging
from datetime import date, datetime
from typing import List, Dict, Optional

class InvestmentParser:
    def __init__(self, qif_dir: str):
        self.qif_dir = qif_dir
        self.logger = logging.getLogger('investment_parser')
        
    def parse_investment_date(self, qif_date_str: str) -> Optional[date]:
        """Parse QIF investment date format."""
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
            
            raise ValueError("Unsupported QIF date format")
        except Exception as e:
            self.logger.warning(f"Bad investment date format: {qif_date_str} ({e})")
            return None
    
    def parse_investment_qif(self) -> pd.DataFrame:
        """Parse investment sections from QIF files."""
        records = []
        files = [f for f in os.listdir(self.qif_dir) if f.lower().endswith('.qif')]
        self.logger.info(f"Found {len(files)} QIF file(s) for investment parsing: {files}")
        
        for fname in files:
            path = os.path.join(self.qif_dir, fname)
            self.logger.info(f"Parsing investment QIF file: {path}")
            
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                
                # Split by account sections
                account_sections = content.split('!Account')
                
                for section in account_sections:
                    if not section.strip():
                        continue
                    
                    # Check if this is an investment account
                    if '!Type:Invst' not in section:
                        continue
                    
                    # Parse account name
                    account_name = ""
                    lines = section.split('\n')
                    for line in lines:
                        if line.startswith('N'):
                            account_name = line[1:].strip()
                            break
                    
                    # Parse investment transactions
                    current_transaction = {}
                    transaction_lines = section.split('^')
                    
                    for transaction_block in transaction_lines:
                        if not transaction_block.strip():
                            continue
                        
                        current_transaction = {}
                        lines = transaction_block.strip().split('\n')
                        
                        for line in lines:
                            line = line.strip()
                            if not line:
                                continue
                            
                            if line.startswith('D'):
                                current_transaction['date'] = line[1:]
                            elif line.startswith('T'):
                                current_transaction['amount'] = line[1:]
                            elif line.startswith('N'):
                                current_transaction['action'] = line[1:]
                            elif line.startswith('Y'):
                                current_transaction['security'] = line[1:]
                            elif line.startswith('I'):
                                current_transaction['price'] = line[1:]
                            elif line.startswith('Q'):
                                current_transaction['quantity'] = line[1:]
                            elif line.startswith('O'):
                                current_transaction['commission'] = line[1:]
                            elif line.startswith('M'):
                                current_transaction['memo'] = line[1:]
                        
                        # Process the transaction if we have enough data
                        if current_transaction and 'date' in current_transaction:
                            # Parse date
                            dt = self.parse_investment_date(current_transaction.get('date', ''))
                            
                            # Parse amount
                            amount = 0.0
                            if 'amount' in current_transaction:
                                try:
                                    amount = float(current_transaction['amount'].replace(',', ''))
                                except Exception as e:
                                    self.logger.warning(f"Bad investment amount: {current_transaction['amount']} in file {fname} ({e})")
                                    amount = 0.0
                            
                            # Parse price
                            price = 0.0
                            if 'price' in current_transaction:
                                try:
                                    price = float(current_transaction['price'].replace(',', ''))
                                except Exception as e:
                                    self.logger.warning(f"Bad investment price: {current_transaction['price']} in file {fname} ({e})")
                                    price = 0.0
                            
                            # Parse quantity
                            quantity = 0.0
                            if 'quantity' in current_transaction:
                                try:
                                    quantity = float(current_transaction['quantity'].replace(',', ''))
                                except Exception as e:
                                    self.logger.warning(f"Bad investment quantity: {current_transaction['quantity']} in file {fname} ({e})")
                                    quantity = 0.0
                            
                            # Parse commission
                            commission = 0.0
                            if 'commission' in current_transaction:
                                try:
                                    commission = float(current_transaction['commission'].replace(',', ''))
                                except Exception as e:
                                    self.logger.warning(f"Bad investment commission: {current_transaction['commission']} in file {fname} ({e})")
                                    commission = 0.0
                            
                            records.append({
                                'date': dt,
                                'security': current_transaction.get('security', ''),
                                'action': current_transaction.get('action', ''),
                                'quantity': quantity,
                                'price': price,
                                'commission': commission,
                                'amount': amount,
                                'memo': current_transaction.get('memo', ''),
                                'account_name': account_name,
                                'source_file': fname
                            })
        
        self.logger.info(f"Parsed total {len(records)} investment transactions")
        df = pd.DataFrame(records)
        return df
    
    def get_portfolio_summary(self, df: pd.DataFrame) -> Dict:
        """Generate portfolio summary from investment data."""
        if df.empty:
            return {}
        
        # Group by security to get current holdings
        holdings = df.groupby('security').agg({
            'quantity': 'sum',
            'price': 'last',
            'amount': 'sum'
        }).reset_index()
        
        # Calculate current values
        holdings['current_value'] = holdings['quantity'] * holdings['price']
        holdings['total_invested'] = holdings['amount']
        holdings['unrealized_gain_loss'] = holdings['current_value'] - holdings['total_invested']
        
        # Filter out zero or negative quantities (sold positions)
        current_holdings = holdings[holdings['quantity'] > 0]
        
        # Calculate portfolio metrics
        total_value = current_holdings['current_value'].sum()
        total_invested = current_holdings['total_invested'].sum()
        total_gain_loss = current_holdings['unrealized_gain_loss'].sum()
        
        # Calculate return percentage
        return_pct = (total_gain_loss / total_invested * 100) if total_invested > 0 else 0
        
        # Get top holdings
        top_holdings = current_holdings.nlargest(10, 'current_value')
        
        return {
            'total_value': round(total_value, 2),
            'total_invested': round(total_invested, 2),
            'total_gain_loss': round(total_gain_loss, 2),
            'return_percentage': round(return_pct, 2),
            'holdings_count': len(current_holdings),
            'top_holdings': top_holdings.to_dict('records')
        }
    
    def get_transaction_summary(self, df: pd.DataFrame) -> Dict:
        """Generate transaction summary from investment data."""
        if df.empty:
            return {}
        
        # Group by action type
        action_summary = df.groupby('action').agg({
            'amount': 'sum',
            'quantity': 'sum',
            'security': 'count'
        }).reset_index()
        
        # Calculate totals
        total_buys = action_summary[action_summary['action'].str.contains('Buy|BuyX', case=False, na=False)]['amount'].sum()
        total_sells = action_summary[action_summary['action'].str.contains('Sell|SellX', case=False, na=False)]['amount'].sum()
        total_dividends = action_summary[action_summary['action'].str.contains('Div|Dividend', case=False, na=False)]['amount'].sum()
        
        return {
            'total_buys': round(total_buys, 2),
            'total_sells': round(total_sells, 2),
            'total_dividends': round(total_dividends, 2),
            'net_investment': round(total_buys - total_sells, 2),
            'action_breakdown': action_summary.to_dict('records')
        }
