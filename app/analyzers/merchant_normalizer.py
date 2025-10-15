import pandas as pd
import re
from typing import List, Dict, Tuple, Optional
from collections import defaultdict
import logging

class MerchantNormalizer:
    def __init__(self, engine):
        self.engine = engine
        self.logger = logging.getLogger('merchant_normalizer')
        
    def clean_merchant_name(self, name: str) -> str:
        """Clean and normalize merchant names."""
        if not name:
            return ""
            
        # Convert to lowercase
        name = name.lower().strip()
        
        # Remove common prefixes/suffixes
        prefixes_to_remove = [
            r'^pos\s+',  # POS transactions
            r'^debit\s+',  # Debit card
            r'^credit\s+',  # Credit card
            r'^ach\s+',  # ACH transfers
            r'^check\s+',  # Check payments
            r'^online\s+',  # Online payments
            r'^mobile\s+',  # Mobile payments
        ]
        
        for prefix in prefixes_to_remove:
            name = re.sub(prefix, '', name, flags=re.IGNORECASE)
        
        # Remove common suffixes
        suffixes_to_remove = [
            r'\s+pos$',  # Point of sale
            r'\s+debit$',  # Debit transactions
            r'\s+credit$',  # Credit transactions
            r'\s+online$',  # Online transactions
            r'\s+mobile$',  # Mobile transactions
            r'\s+app$',  # App transactions
        ]
        
        for suffix in suffixes_to_remove:
            name = re.sub(suffix, '', name, flags=re.IGNORECASE)
        
        # Remove extra whitespace and special characters
        name = re.sub(r'\s+', ' ', name)
        name = re.sub(r'[^\w\s\-&]', '', name)
        
        return name.strip()
    
    def extract_merchant_keywords(self, name: str) -> List[str]:
        """Extract key words from merchant name for matching."""
        cleaned = self.clean_merchant_name(name)
        
        # Split into words and filter out common words
        words = cleaned.split()
        
        # Common words to ignore
        ignore_words = {
            'the', 'and', 'of', 'for', 'in', 'on', 'at', 'to', 'from', 'with',
            'inc', 'llc', 'corp', 'ltd', 'co', 'company', 'store', 'shop',
            'restaurant', 'cafe', 'bar', 'grill', 'pizza', 'food'
        }
        
        # Filter out short words and common words
        keywords = [word for word in words 
                   if len(word) > 2 and word not in ignore_words]
        
        return keywords
    
    def simple_fuzzy_match(self, name1: str, name2: str, threshold: float = 0.8) -> float:
        """Simple fuzzy matching based on keyword overlap."""
        keywords1 = set(self.extract_merchant_keywords(name1))
        keywords2 = set(self.extract_merchant_keywords(name2))
        
        if not keywords1 or not keywords2:
            return 0.0
        
        # Calculate Jaccard similarity
        intersection = len(keywords1.intersection(keywords2))
        union = len(keywords1.union(keywords2))
        
        if union == 0:
            return 0.0
        
        return intersection / union
    
    def find_similar_merchants(self, merchant_name: str, existing_merchants: List[Dict], 
                             threshold: float = 0.7) -> List[Tuple[str, float]]:
        """Find similar merchants using fuzzy matching."""
        matches = []
        
        for merchant in existing_merchants:
            canonical_name = merchant['canonical_name']
            similarity = self.simple_fuzzy_match(merchant_name, canonical_name, threshold)
            
            if similarity >= threshold:
                matches.append((canonical_name, similarity))
        
        # Sort by similarity score
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches
    
    def normalize_merchants(self) -> Dict[str, str]:
        """Normalize all merchant names in the database."""
        # Get all unique merchant names
        query = """
        SELECT DISTINCT payee 
        FROM transactions 
        WHERE payee IS NOT NULL AND payee != ''
        ORDER BY payee
        """
        
        df = pd.read_sql(query, self.engine)
        unique_merchants = df['payee'].tolist()
        
        self.logger.info(f"Found {len(unique_merchants)} unique merchants to normalize")
        
        # Create merchants table if it doesn't exist
        self._create_merchants_table()
        
        # Get existing canonical merchants
        existing_merchants = self._get_existing_merchants()
        
        # Normalize merchants
        merchant_mappings = {}
        new_canonical_merchants = []
        
        for merchant in unique_merchants:
            cleaned_name = self.clean_merchant_name(merchant)
            
            if not cleaned_name:
                continue
            
            # Check if we already have a mapping for this merchant
            if merchant in merchant_mappings:
                continue
            
            # Look for similar existing merchants
            similar_merchants = self.find_similar_merchants(cleaned_name, existing_merchants)
            
            if similar_merchants:
                # Use the most similar existing merchant
                canonical_name = similar_merchants[0][0]
                merchant_mappings[merchant] = canonical_name
            else:
                # Create new canonical merchant
                canonical_name = cleaned_name
                merchant_mappings[merchant] = canonical_name
                new_canonical_merchants.append({
                    'canonical_name': canonical_name,
                    'original_name': merchant,
                    'transaction_count': 0  # Will be updated later
                })
        
        # Save mappings to database
        self._save_merchant_mappings(merchant_mappings, new_canonical_merchants)
        
        self.logger.info(f"Normalized {len(merchant_mappings)} merchants into {len(set(merchant_mappings.values()))} canonical names")
        
        return merchant_mappings
    
    def _create_merchants_table(self):
        """Create the merchants table if it doesn't exist."""
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS merchants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_name TEXT UNIQUE NOT NULL,
            original_name TEXT,
            transaction_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        
        with self.engine.connect() as conn:
            conn.execute(create_table_sql)
            conn.commit()
    
    def _get_existing_merchants(self) -> List[Dict]:
        """Get existing canonical merchants from the database."""
        query = "SELECT canonical_name, transaction_count FROM merchants"
        
        try:
            df = pd.read_sql(query, self.engine)
            return df.to_dict('records')
        except Exception:
            return []
    
    def _save_merchant_mappings(self, mappings: Dict[str, str], new_merchants: List[Dict]):
        """Save merchant mappings to the database."""
        with self.engine.connect() as conn:
            # Insert new canonical merchants
            for merchant in new_merchants:
                insert_sql = """
                INSERT OR IGNORE INTO merchants (canonical_name, original_name, transaction_count)
                VALUES (?, ?, ?)
                """
                conn.execute(insert_sql, (
                    merchant['canonical_name'],
                    merchant['original_name'],
                    merchant['transaction_count']
                ))
            
            # Update transaction counts for all merchants
            for canonical_name in set(mappings.values()):
                count_sql = """
                SELECT COUNT(*) FROM transactions 
                WHERE payee IN (
                    SELECT original_name FROM merchants WHERE canonical_name = ?
                )
                """
                result = conn.execute(count_sql, (canonical_name,))
                count = result.fetchone()[0]
                
                update_sql = "UPDATE merchants SET transaction_count = ? WHERE canonical_name = ?"
                conn.execute(update_sql, (count, canonical_name))
            
            conn.commit()
    
    def get_merchant_statistics(self) -> Dict:
        """Get statistics about merchant normalization."""
        query = """
        SELECT 
            COUNT(*) as total_merchants,
            COUNT(DISTINCT canonical_name) as canonical_merchants,
            AVG(transaction_count) as avg_transactions_per_merchant,
            MAX(transaction_count) as max_transactions
        FROM merchants
        """
        
        try:
            df = pd.read_sql(query, self.engine)
            if not df.empty:
                return df.iloc[0].to_dict()
        except Exception as e:
            self.logger.warning(f"Failed to get merchant statistics: {e}")
        
        return {}
    
    def get_top_merchants(self, limit: int = 20) -> List[Dict]:
        """Get top merchants by transaction count."""
        query = """
        SELECT canonical_name, transaction_count, original_name
        FROM merchants 
        ORDER BY transaction_count DESC 
        LIMIT ?
        """
        
        try:
            df = pd.read_sql(query, self.engine, params=(limit,))
            return df.to_dict('records')
        except Exception as e:
            self.logger.warning(f"Failed to get top merchants: {e}")
            return []
