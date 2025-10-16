import os
import logging
import pandas as pd
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple


class MasterListsParser:
    def __init__(self, qif_dir: str):
        self.qif_dir = qif_dir
        self.logger = logging.getLogger('master_lists_parser')

    def _parse_date(self, qif_date_str: str) -> Optional[date]:
        try:
            q = (qif_date_str or '').strip()
            if not q:
                return None
            if "'" in q:
                parts = q.split("'")
                if len(parts) == 2:
                    mmdd, yy_or_yyyy = parts
                    month, day = [int(x) for x in mmdd.split('/')]
                    if len(yy_or_yyyy) == 2:
                        yy = int(yy_or_yyyy)
                        year = 1900 + yy if yy >= 70 else 2000 + yy
                    else:
                        year = int(yy_or_yyyy)
                    return date(year, month, day)
            for fmt in ("%m/%d/%Y", "%m/%d/%y", "%m/%e/%Y", "%m/%e/%y"):
                try:
                    return datetime.strptime(q, fmt).date()
                except Exception:
                    pass
        except Exception:
            pass
        return None

    def parse(self) -> Dict[str, pd.DataFrame]:
        tags: List[Dict] = []
        categories: List[Dict] = []
        securities: List[Dict] = []
        prices: List[Dict] = []
        memorized: List[Dict] = []

        files = [f for f in os.listdir(self.qif_dir) if f.lower().endswith('.qif')]
        self.logger.info(f"Scanning {len(files)} QIF file(s) for master lists: {files}")

        for fname in files:
            path = os.path.join(self.qif_dir, fname)
            current_section = None  # Tag|Cat|Security|Prices|Memorized|other
            price_block = {}  # holds S,D,P until ^
            memo_block = {}   # holds M,L,T until ^
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    for raw in f:
                        line = raw.strip()
                        if not line:
                            continue
                        if line.startswith('!Type:'):
                            t = line[6:].strip()
                            # Normalize common names
                            if t.lower().startswith('tag'):
                                current_section = 'Tag'
                            elif t.lower().startswith('cat'):
                                current_section = 'Cat'
                            elif t.lower().startswith('security'):
                                current_section = 'Security'
                            elif t.lower().startswith('prices'):
                                current_section = 'Prices'
                            elif t.lower().startswith('memorized'):
                                current_section = 'Memorized'
                            else:
                                current_section = None
                            # reset any open blocks
                            price_block = {}
                            memo_block = {}
                            continue

                        if current_section == 'Tag':
                            # Records separated by ^; minimal fields N (name), M (note)
                            if line == '^':
                                continue
                            if line.startswith('N'):
                                tags.append({'name': line[1:].strip(), 'note': ''})
                            elif line.startswith('M') and tags:
                                if tags[-1].get('note', '') == '':
                                    tags[-1]['note'] = line[1:].strip()

                        elif current_section == 'Cat':
                            if line == '^':
                                continue
                            if line.startswith('N'):
                                full = line[1:].strip()
                                parent = ''
                                if ':' in full:
                                    parent = full.split(':', 1)[0]
                                categories.append({'name': full, 'parent': parent, 'tax_line': ''})
                            # Some exports may include tax line info with 'T' or similar; ignore unknowns safely

                        elif current_section == 'Security':
                            if line == '^':
                                continue
                            if line.startswith('N'):
                                # Begin new security row
                                securities.append({'name': line[1:].strip(), 'symbol': '', 'type': ''})
                            elif line.startswith('S') and securities:
                                if securities[-1]['symbol'] == '':
                                    securities[-1]['symbol'] = line[1:].strip()
                            elif line.startswith('T') and securities:
                                if securities[-1]['type'] == '':
                                    securities[-1]['type'] = line[1:].strip()

                        elif current_section == 'Prices':
                            if line == '^':
                                # finalize any accumulated price block
                                if price_block.get('symbol') and price_block.get('date') and price_block.get('price') is not None:
                                    prices.append({
                                        'security': price_block.get('security', ''),
                                        'symbol': price_block.get('symbol'),
                                        'date': self._parse_date(price_block.get('date')),
                                        'price': self._safe_float(price_block.get('price')),
                                        'source_file': fname,
                                    })
                                price_block = {}
                                continue
                            if line.startswith('S'):
                                price_block['symbol'] = line[1:].strip()
                            elif line.startswith('N'):
                                price_block['security'] = line[1:].strip()
                            elif line.startswith('D'):
                                price_block['date'] = line[1:].strip()
                            elif line.startswith('P'):
                                price_block['price'] = line[1:].strip()
                            else:
                                # Some exports may provide CSV-like price lines; try naive parse
                                # e.g., SYM,mm/dd'yyyy,123.45
                                parts = [p.strip().strip('"') for p in line.split(',')]
                                if len(parts) >= 3:
                                    sym, dt, pr = parts[0], parts[1], parts[2]
                                    prices.append({
                                        'security': price_block.get('security', ''),
                                        'symbol': sym,
                                        'date': self._parse_date(dt),
                                        'price': self._safe_float(pr),
                                        'source_file': fname,
                                    })

                        elif current_section == 'Memorized':
                            if line == '^':
                                if memo_block.get('payee'):
                                    memorized.append({
                                        'payee': memo_block.get('payee', ''),
                                        'category': memo_block.get('category', ''),
                                        'memo': memo_block.get('memo', ''),
                                        'amount': self._safe_float(memo_block.get('amount')),
                                    })
                                memo_block = {}
                                continue
                            if line.startswith('M'):
                                memo_block['payee'] = line[1:].strip()
                            elif line.startswith('L'):
                                memo_block['category'] = line[1:].strip()
                            elif line.startswith('T'):
                                memo_block['amount'] = line[1:].strip()
                            elif line.startswith('N'):
                                # Some variants use N for payee name
                                memo_block['payee'] = line[1:].strip()
                            elif line.startswith('K'):
                                # some variants use K for memo/description
                                memo_block['memo'] = line[1:].strip()
                            elif line.startswith('Q'):
                                # ignore quantities here
                                pass
            except Exception as e:
                self.logger.warning(f"Failed reading {path}: {e}")

        # De-duplicate by primary key expectations
        df_tags = pd.DataFrame(tags).drop_duplicates(subset=['name']) if tags else pd.DataFrame(columns=['name', 'note'])
        df_categories = pd.DataFrame(categories).drop_duplicates(subset=['name']) if categories else pd.DataFrame(columns=['name', 'parent', 'tax_line'])
        # Prefer unique symbols where present; else unique names
        if securities:
            tmp = pd.DataFrame(securities)
            if 'symbol' in tmp and tmp['symbol'].fillna('').str.len().gt(0).any():
                tmp = tmp.sort_values(['symbol', 'name']).drop_duplicates(subset=['symbol'], keep='first')
            else:
                tmp = tmp.sort_values(['name']).drop_duplicates(subset=['name'], keep='first')
            df_securities = tmp.reset_index(drop=True)
        else:
            df_securities = pd.DataFrame(columns=['name', 'symbol', 'type'])

        # Prices: drop rows missing symbol or date or price
        if prices:
            df_prices = pd.DataFrame(prices)
            df_prices = df_prices.dropna(subset=['symbol', 'date', 'price'])
            df_prices = df_prices.drop_duplicates(subset=['symbol', 'date'])
        else:
            df_prices = pd.DataFrame(columns=['security', 'symbol', 'date', 'price', 'source_file'])

        if memorized:
            df_mem = pd.DataFrame(memorized)
            df_mem = df_mem.dropna(subset=['payee']).drop_duplicates(subset=['payee'])
        else:
            df_mem = pd.DataFrame(columns=['payee', 'category', 'memo', 'amount'])

        return {
            'tags': df_tags,
            'categories': df_categories,
            'securities': df_securities,
            'prices': df_prices,
            'memorized': df_mem,
        }

    def _safe_float(self, s: Optional[str]) -> Optional[float]:
        if s is None:
            return None
        try:
            return float(str(s).replace(',', '').strip())
        except Exception:
            return None


