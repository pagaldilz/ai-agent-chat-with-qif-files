import pandas as pd
import re
from typing import List, Dict, Tuple, Optional
from collections import defaultdict
import logging
from sqlalchemy import text
import json

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
    
    def normalize_merchants(self) -> List[Dict]:
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
                    'original_names': [merchant], # Ensure it's a list of original names
                    'transaction_count': 0  # Will be updated later
                })
        
        # Save mappings to database
        self._save_merchant_mappings(merchant_mappings, new_canonical_merchants)
        
        self.logger.info(f"Normalized {len(merchant_mappings)} merchants into {len(set(merchant_mappings.values()))} canonical names")
        
        # Convert mappings to list of dictionaries for API response
        mappings_list = []
        for original, canonical in merchant_mappings.items():
            mappings_list.append({
                'original_name': original,
                'canonical_name': canonical
            })
        
        return mappings_list
    
    def _create_merchants_table(self):
        """Create the merchants table if it doesn't exist."""
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS merchants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_name TEXT UNIQUE NOT NULL,
            original_names TEXT, -- Storing JSON array of original names
            transaction_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        
        with self.engine.connect() as conn:
            conn.execute(text(create_table_sql))
            conn.commit()
    
    def _get_existing_merchants(self) -> List[Dict]:
        """Get existing canonical merchants from the database."""
        query = "SELECT canonical_name, original_names, transaction_count FROM merchants"
        
        try:
            df = pd.read_sql(query, self.engine)
            if df.empty:
                return []
            
            # Convert DataFrame to list of dictionaries, handling NaN values and JSON parsing
            records = []
            for _, row in df.iterrows():
                record = {}
                for col in df.columns:
                    value = row[col]
                    if pd.isna(value):
                        record[col] = None
                    else:
                        if col == 'original_names' and isinstance(value, str):
                            try:
                                record[col] = json.loads(value)
                            except json.JSONDecodeError:
                                self.logger.error(f"Failed to decode JSON for original_names: {value}")
                                record[col] = [] # Default to empty list on error
                        else:
                            record[col] = value
                records.append(record)
            return records
        except Exception as e:
            self.logger.warning(f"Failed to get existing merchants: {e}")
            return []
    
    def _save_merchant_mappings(self, mappings: Dict[str, str], new_canonical_merchants: List[Dict]):
        """Save merchant mappings to the database."""
        with self.engine.connect() as conn:
            # Fetch existing mappings for updating
            existing_canonical_map = {m['canonical_name']: set(m['original_names']) for m in self._get_existing_merchants()}
            
            # Process new canonical merchants and update existing ones
            for merchant_dict in new_canonical_merchants:
                canonical_name = merchant_dict['canonical_name']
                original_name = merchant_dict['original_names'][0] # Access the first original name from the list
                
                if canonical_name not in existing_canonical_map:
                    # Insert new canonical merchant
                    insert_sql = """
                    INSERT INTO merchants (canonical_name, original_names, transaction_count)
                    VALUES (:canonical_name, :original_names, :transaction_count)
                    """
                    conn.execute(text(insert_sql), {
                        'canonical_name': canonical_name,
                        'original_names': json.dumps([original_name]),
                        'transaction_count': 0  # Will be updated later
                    })
                    existing_canonical_map[canonical_name] = {original_name}
                else:
                    # Update existing canonical merchant with new original name
                    if original_name not in existing_canonical_map[canonical_name]:
                        existing_canonical_map[canonical_name].add(original_name)
                        update_sql = """
                        UPDATE merchants 
                        SET original_names = :original_names
                        WHERE canonical_name = :canonical_name
                        """
                        conn.execute(text(update_sql), {
                            'original_names': json.dumps(list(existing_canonical_map[canonical_name])),
                            'canonical_name': canonical_name
                        })
            
            # Update transaction counts for all canonical merchants based on all their original names
            for canonical_name in set(mappings.values()):
                # Get all original names associated with this canonical name
                # This needs to query the DB directly to get the latest list after potential updates
                select_original_names_sql = "SELECT original_names FROM merchants WHERE canonical_name = :canonical_name"
                result = conn.execute(text(select_original_names_sql), {'canonical_name': canonical_name}).fetchone()
                
                if result and result[0]:
                    original_names_for_canonical = json.loads(result[0])
                    
                    # Recalculate transaction count for all associated original names
                    if original_names_for_canonical:
                        # Create a list of parameters for the IN clause
                        placeholders = ', '.join([f':original_name_{i}' for i in range(len(original_names_for_canonical))])
                        params = {f'original_name_{i}': name for i, name in enumerate(original_names_for_canonical)}

                        count_sql = f"""
                        SELECT COUNT(*) FROM transactions 
                        WHERE payee IN ({placeholders})
                        """
                        result_count = conn.execute(text(count_sql), params).fetchone()
                        count = result_count[0] if result_count else 0
                    else:
                        count = 0
                else:
                    count = 0
                
                update_sql = "UPDATE merchants SET transaction_count = :count WHERE canonical_name = :canonical_name"
                conn.execute(text(update_sql), {'count': count, 'canonical_name': canonical_name})
            
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
                row = df.iloc[0]
                # Handle None values properly
                stats = {}
                for col in df.columns:
                    value = row[col]
                    if pd.isna(value) or value is None:
                        stats[col] = 0 if col in ['total_merchants', 'canonical_merchants', 'max_transactions'] else 0.0
                    else:
                        stats[col] = value
                return stats
        except Exception as e:
            self.logger.warning(f"Failed to get merchant statistics: {e}")
        
        return {}
    
    def get_top_merchants(self, limit: int = 20) -> List[Dict]:
        """Get top merchants by transaction count."""
        query = """
        SELECT canonical_name, transaction_count, original_names
        FROM merchants 
        ORDER BY transaction_count DESC 
        LIMIT ?
        """
        
        try:
            df = pd.read_sql(query, self.engine, params=[limit])
            if df.empty:
                return []
            
            # Convert DataFrame to list of dictionaries, handling NaN values and JSON parsing
            records = []
            for _, row in df.iterrows():
                record = {}
                for col in df.columns:
                    value = row[col]
                    if pd.isna(value):
                        record[col] = None
                    else:
                        if col == 'original_names' and isinstance(value, str):
                            try:
                                record[col] = json.loads(value)
                            except json.JSONDecodeError:
                                self.logger.error(f"Failed to decode JSON for original_names: {value}")
                                record[col] = [] # Default to empty list on error
                        else:
                            record[col] = value
                records.append(record)
            return records
        except Exception as e:
            self.logger.warning(f"Failed to get top merchants: {e}")
            return []
