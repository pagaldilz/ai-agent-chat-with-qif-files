import argparse
import hashlib
import logging
import os
import re
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

# Configure logging
logger = logging.getLogger(__name__)

try:
    import pdfplumber  # type: ignore
except Exception:  # pragma: no cover
    pdfplumber = None  # type: ignore

try:
    from rapidfuzz import fuzz  # type: ignore
except Exception:  # pragma: no cover
    fuzz = None  # type: ignore

try:
    import requests
    import json
except Exception:  # pragma: no cover
    requests = None  # type: ignore
    json = None  # type: ignore


DATE_PATTERNS: List[re.Pattern] = [
    re.compile(r"(\d{4})[-/](\d{2})[-/](\d{2})"),
    re.compile(r"(\d{2})[-/](\d{2})[-/](\d{4})"),
    re.compile(r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+(\d{4})", re.IGNORECASE),
]


DOC_TYPE_RULES: Dict[str, List[str]] = {
    "capital_account": ["capital account", "capital statement"],
    "capital_call": ["capital call", "drawdown", "notice of capital call"],
    "distribution": ["distribution notice", "distribution", "capital distribution"],
    "report": ["quarterly report", "annual report", r"q\d report", "financial statements"],
}


METRIC_PATTERNS: Dict[str, List[re.Pattern]] = {
    "nav": [re.compile(r"\bnav\b\s*[:=-]?\s*\$?([\d,]+\.?\d*)", re.IGNORECASE)],
    "unfunded": [re.compile(r"unfunded\s*(commitment)?\b\s*[:=-]?\s*\$?([\d,]+\.?\d*)", re.IGNORECASE)],
    "irr_net": [re.compile(r"\bnet\s*irr\b\s*[:=-]?\s*([\d\.]+)%", re.IGNORECASE)],
    "tvpi": [re.compile(r"\btvpi\b\s*[:=-]?\s*([\d\.]+)", re.IGNORECASE)],
    "dpi": [re.compile(r"\bdpi\b\s*[:=-]?\s*([\d\.]+)", re.IGNORECASE)],
    "rvpi": [re.compile(r"\brvpi\b\s*[:=-]?\s*([\d\.]+)", re.IGNORECASE)],
}


@dataclass
class ParsedDocument:
    fund_name: str
    as_of_date: Optional[str]
    doc_type: str
    pages: int
    metrics: Dict[str, Optional[float]]
    cash_flows: List[Tuple[str, float, str, str]]
    parse_confidence: float


def slugify(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return re.sub(r"-+", "-", cleaned)


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_text_pages(path: str) -> List[str]:
    if pdfplumber is None:
        raise RuntimeError("pdfplumber is required for text-only PDF extraction.")
    pages: List[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""
            pages.append(text)
    return pages


def detect_as_of_date(pages: List[str]) -> Optional[str]:
    for page in pages[:3]:
        for pattern in DATE_PATTERNS:
            m = pattern.search(page)
            if not m:
                continue
            try:
                if len(m.groups()) == 3 and len(m.group(1)) == 4:
                    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
                if len(m.groups()) == 3 and len(m.group(3)) == 4:
                    mm = int(m.group(1))
                    dd = int(m.group(2))
                    yyyy = int(m.group(3))
                    return f"{yyyy:04d}-{mm:02d}-{dd:02d}"
                if len(m.groups()) == 3 and m.group(2):
                    month_map = {
                        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
                        "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
                    }
                    mm = month_map[m.group(2).lower()]
                    dd = int(m.group(1))
                    yyyy = int(m.group(3))
                    return f"{yyyy:04d}-{mm:02d}-{dd:02d}"
            except Exception:
                continue
    return None


def classify_doc_type(pages: List[str]) -> str:
    header = "\n".join(pages[:2]).lower()
    for label, keywords in DOC_TYPE_RULES.items():
        for kw in keywords:
            if kw in header:
                return label
    return "report"


def detect_fund_name(pages: List[str]) -> str:
    candidates: List[str] = []
    for page in pages[:2]:
        lines = [l.strip() for l in page.splitlines() if l.strip()]
        for line in lines[:15]:  # Look at more lines
            if len(line) < 200:
                # Look for fund names with various patterns
                if any(tok in line.lower() for tok in ["fund", "lp", "partners", "capital", "index", "lifepath", "target"]):
                    # Prioritize lines that look like fund names
                    if (line.count(" ") >= 2 and  # Multi-word names
                        not line.lower().startswith(("as of", "total", "the fund", "custom benchmark")) and
                        not line.lower().endswith(("benchmark", "category", "rating"))):
                        candidates.append(line)
    
    if candidates:
        # Sort by relevance: prefer longer names with "fund" or "index"
        def score_candidate(s):
            score = len(s)
            if "fund" in s.lower():
                score += 50
            if "index" in s.lower():
                score += 30
            if "lifepath" in s.lower():
                score += 100
            return score
        
        return sorted(candidates, key=score_candidate, reverse=True)[0]
    return "Unknown Fund"


def parse_metrics(pages: List[str]) -> Dict[str, Optional[float]]:
    text = "\n".join(pages)
    result: Dict[str, Optional[float]] = {k: None for k in METRIC_PATTERNS.keys()}
    for key, patterns in METRIC_PATTERNS.items():
        for pattern in patterns:
            m = pattern.search(text)
            if m:
                val = m.group(1 if key != "unfunded" else 2)
                try:
                    num = float(str(val).replace(",", ""))
                except Exception:
                    continue
                result[key] = num
                break
    return result


def parse_cash_flows(pages: List[str]) -> List[Tuple[str, float, str, str]]:
    flows: List[Tuple[str, float, str, str]] = []
    for page in pages:
        for line in page.splitlines():
            line_l = line.lower()
            date_match = None
            for pattern in DATE_PATTERNS:
                m = pattern.search(line)
                if m:
                    date_match = m
                    break
            if not date_match:
                continue
            normalized_date = None
            try:
                if len(date_match.groups()) == 3 and len(date_match.group(1)) == 4:
                    normalized_date = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}"
                elif len(date_match.groups()) == 3 and len(date_match.group(3)) == 4:
                    mm = int(date_match.group(1))
                    dd = int(date_match.group(2))
                    yyyy = int(date_match.group(3))
                    normalized_date = f"{yyyy:04d}-{mm:02d}-{dd:02d}"
            except Exception:
                continue

            amt_match = re.search(r"([\-\$]?\$?[\d,]+\.?\d*)", line)
            if not normalized_date or not amt_match:
                continue
            amt_str = amt_match.group(1)
            try:
                amount = float(amt_str.replace("$", "").replace(",", ""))
            except Exception:
                continue
            flow_type = "distribution" if any(k in line_l for k in ["distribution", "dist"]) else "capital_call" if any(k in line_l for k in ["call", "drawdown"]) else "fee" if "fee" in line_l else "unknown"
            desc = line.strip()
            flows.append((normalized_date, amount, flow_type, desc))
    return flows


def extract_with_llm(pages: List[str], llm_provider: str = "ollama", llm_model: str = "phi4-mini:3.8b", 
                    ollama_url: str = "http://localhost:11434", lmstudio_base_url: str = "http://localhost:1234/v1",
                    openai_api_key: str = None, azure_openai_endpoint: str = None, 
                    azure_openai_api_key: str = None, azure_openai_deployment: str = None) -> Dict[str, object]:
    """
    Extract fund data using LLM with structured prompt.
    Returns standardized dict matching pattern extraction format.
    """
    if not pages or not any(page.strip() for page in pages):
        logger.warning("No text content available for LLM extraction")
        return {"fund_name": "Unknown Fund", "as_of_date": None, "doc_type": "report", 
                "metrics": {}, "cash_flows": [], "extraction_method": "llm", "confidence": 0.5}
    
    # Prepare text for LLM (first 3 pages, truncated)
    text_content = "\n".join(pages[:3])
    if len(text_content) > 8000:  # Truncate to avoid token limits
        text_content = text_content[:8000] + "..."
    
    prompt = f"""Extract ALL relevant financial and fund information from this document.
Return ONLY valid JSON with this comprehensive structure:
{{
  "fund_name": "Full fund name as it appears",
  "as_of_date": "YYYY-MM-DD or null",
  "doc_type": "capital_account|distribution|capital_call|report|fact_sheet|prospectus|quarterly_report|annual_report",
  "fund_type": "private_equity|mutual_fund|target_date|hedge_fund|venture_capital|real_estate|other",
  "fund_manager": "Name of fund manager or management company",
  "vintage_year": "Year fund was established or null",
  "strategy": "Investment strategy description",
  "total_assets": "Total fund assets under management",
  "expense_ratio": "Annual expense ratio percentage",
  "minimum_investment": "Minimum investment amount required",
  "performance_metrics": {{
    "nav": "Net Asset Value",
    "unfunded": "Unfunded commitments",
    "irr_net": "Net Internal Rate of Return percentage",
    "irr_gross": "Gross Internal Rate of Return percentage", 
    "tvpi": "Total Value to Paid-In multiple",
    "dpi": "Distributions to Paid-In multiple",
    "rvpi": "Residual Value to Paid-In multiple",
    "pme": "Public Market Equivalent",
    "alpha": "Alpha performance metric",
    "beta": "Beta performance metric",
    "sharpe_ratio": "Sharpe ratio",
    "volatility": "Volatility percentage",
    "max_drawdown": "Maximum drawdown percentage",
    "tracking_error": "Tracking error percentage"
  }},
  "asset_allocation": {{
    "equity_percentage": "Percentage in equity",
    "fixed_income_percentage": "Percentage in fixed income", 
    "cash_percentage": "Percentage in cash",
    "alternatives_percentage": "Percentage in alternative investments",
    "international_percentage": "Percentage in international markets"
  }},
  "fees": {{
    "management_fee": "Annual management fee percentage",
    "performance_fee": "Performance fee/carried interest percentage",
    "administrative_fee": "Administrative fee percentage",
    "other_fees": "Other fees and expenses"
  }},
  "ratings": {{
    "morningstar_rating": "Morningstar star rating (1-5)",
    "morningstar_analyst_rating": "Morningstar analyst rating",
    "lipper_rating": "Lipper rating",
    "other_ratings": "Other third-party ratings"
  }},
  "risk_metrics": {{
    "risk_level": "Conservative|Moderate|Aggressive|Very_Aggressive",
    "standard_deviation": "Standard deviation percentage",
    "var_95": "Value at Risk 95%",
    "var_99": "Value at Risk 99%"
  }},
  "cash_flows": [
    {{"date": "YYYY-MM-DD", "amount": 100.0, "type": "distribution|capital_call|fee|dividend|interest", "description": "Description of cash flow"}}
  ],
  "key_dates": {{
    "inception_date": "Fund inception date",
    "next_distribution": "Next expected distribution date",
    "next_capital_call": "Next expected capital call date",
    "reporting_period_end": "End of reporting period"
  }},
  "additional_info": {{
    "investment_minimum": "Minimum investment amount",
    "redemption_frequency": "How often redemptions are allowed",
    "lockup_period": "Lockup period in months",
    "geographic_focus": "Primary geographic focus",
    "sector_focus": "Primary sector focus",
    "benchmark": "Benchmark used for comparison",
    "custom_benchmark": "Custom benchmark description"
  }}
}}

Extract as much information as possible. If a field is not found or not applicable, use null.
Document text:
{text_content}"""
    
    try:
        if llm_provider == "ollama":
            response = requests.post(
                f"{ollama_url}/api/generate",
                json={"model": llm_model, "prompt": prompt, "options": {"temperature": 0}},
                timeout=120,
            )
            if response.status_code != 200:
                raise Exception(f"Ollama error: {response.text}")
            
            llm_response = ""
            for line in response.iter_lines():
                if not line:
                    continue
                try:
                    obj = json.loads(line.decode('utf-8'))
                    llm_response += obj.get("response", "")
                except Exception:
                    continue
        
        elif llm_provider == "lmstudio":
            # LM Studio uses OpenAI-compatible API
            import openai
            client = openai.OpenAI(api_key="lm-studio", base_url=lmstudio_base_url)
            completion = client.chat.completions.create(
                model=llm_model,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
            llm_response = completion.choices[0].message.content or ""
        
        elif llm_provider == "openai":
            import openai
            client = openai.OpenAI(api_key=openai_api_key)
            completion = client.chat.completions.create(
                model=llm_model,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
            llm_response = completion.choices[0].message.content or ""
        
        elif llm_provider == "azure":
            import openai
            client = openai.OpenAI(
                api_key=azure_openai_api_key,
                base_url=f"{azure_openai_endpoint}/openai/deployments/{azure_openai_deployment}",
            )
            completion = client.chat.completions.create(
                model=llm_model,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
            llm_response = completion.choices[0].message.content or ""
        
        else:
            raise Exception(f"Unsupported LLM provider: {llm_provider}")
        
        # Parse JSON response
        llm_response = llm_response.strip()
        if llm_response.startswith("```json"):
            llm_response = llm_response[7:]
        if llm_response.endswith("```"):
            llm_response = llm_response[:-3]
        
        result = json.loads(llm_response)
        
        # Convert to standard format - extract basic metrics for compatibility
        performance_metrics = result.get("performance_metrics", {})
        basic_metrics = {
            "nav": performance_metrics.get("nav"),
            "unfunded": performance_metrics.get("unfunded"),
            "irr_net": performance_metrics.get("irr_net"),
            "tvpi": performance_metrics.get("tvpi"),
            "dpi": performance_metrics.get("dpi"),
            "rvpi": performance_metrics.get("rvpi")
        }
        
        cash_flows = []
        for cf in result.get("cash_flows", []):
            cash_flows.append((cf.get("date", ""), cf.get("amount", 0.0), cf.get("type", "unknown"), cf.get("description", "")))
        
        confidence = 0.8  # LLM extraction gets higher confidence
        if basic_metrics.get("nav") or basic_metrics.get("irr_net"):
            confidence = 0.9
        
        logger.info(f"LLM extraction successful: fund='{result.get('fund_name')}', confidence={confidence}")
        
        return {
            "fund_name": result.get("fund_name", "Unknown Fund"),
            "as_of_date": result.get("as_of_date"),
            "doc_type": result.get("doc_type", "report"),
            "metrics": basic_metrics,
            "cash_flows": cash_flows,
            "extraction_method": "llm",
            "confidence": confidence,
            # Store the full comprehensive extraction
            "comprehensive_data": result
        }
        
    except Exception as e:
        logger.error(f"LLM extraction failed: {e}")
        return {
            "fund_name": "Unknown Fund", 
            "as_of_date": None, 
            "doc_type": "report",
            "metrics": {}, 
            "cash_flows": [], 
            "extraction_method": "llm_failed",
            "confidence": 0.3,
            "error": str(e)
        }


def ensure_schema(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS funds (
            id INTEGER PRIMARY KEY,
            slug TEXT UNIQUE,
            name TEXT,
            manager TEXT,
            vintage_year INTEGER,
            strategy TEXT,
            created_at TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS fund_documents (
            id INTEGER PRIMARY KEY,
            fund_id INTEGER,
            file_path TEXT,
            file_hash TEXT UNIQUE,
            doc_type TEXT,
            as_of_date TEXT,
            pages INTEGER,
            ingested_at TEXT,
            parse_status TEXT,
            parse_confidence REAL,
            extraction_method TEXT,
            FOREIGN KEY(fund_id) REFERENCES funds(id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS fund_performance_snapshots (
            id INTEGER PRIMARY KEY,
            fund_id INTEGER,
            as_of_date TEXT,
            nav REAL,
            unfunded REAL,
            irr_net REAL,
            tvpi REAL,
            dpi REAL,
            rvpi REAL,
            pme REAL,
            source_document_id INTEGER,
            UNIQUE(fund_id, as_of_date),
            FOREIGN KEY(fund_id) REFERENCES funds(id),
            FOREIGN KEY(source_document_id) REFERENCES fund_documents(id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS fund_cash_flows (
            id INTEGER PRIMARY KEY,
            fund_id INTEGER,
            flow_date TEXT,
            amount REAL,
            flow_type TEXT,
            description TEXT,
            source_document_id INTEGER,
            source_row_hash TEXT,
            UNIQUE(fund_id, flow_date, amount, flow_type, source_row_hash),
            FOREIGN KEY(fund_id) REFERENCES funds(id),
            FOREIGN KEY(source_document_id) REFERENCES fund_documents(id)
        )
        """
    )
    conn.commit()


def fuzzy_match_fund(conn: sqlite3.Connection, candidate_name: str) -> Optional[int]:
    cur = conn.cursor()
    cur.execute("SELECT id, slug, name FROM funds")
    rows = cur.fetchall()
    if not rows:
        return None
    candidate_slug = slugify(candidate_name)
    best_id: Optional[int] = None
    best_score = -1
    for fund_id, slug_val, name_val in rows:
        if fuzz is None:
            score = 100 if slug_val == candidate_slug or (name_val or "").lower() == candidate_name.lower() else 0
        else:
            score = max(
                fuzz.token_set_ratio(candidate_slug, slug_val or ""),
                fuzz.token_set_ratio(candidate_name.lower(), (name_val or "").lower()),
            )
        if score > best_score:
            best_id, best_score = fund_id, score
    return best_id if best_score >= 90 else None


def get_or_create_fund(conn: sqlite3.Connection, fund_name: str) -> int:
    fund_id = fuzzy_match_fund(conn, fund_name)
    if fund_id is not None:
        return fund_id
    slug = slugify(fund_name)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO funds(slug, name, created_at) VALUES(?, ?, ?)",
        (slug, fund_name, datetime.utcnow().isoformat()),
    )
    conn.commit()
    cur.execute("SELECT id FROM funds WHERE slug = ?", (slug,))
    row = cur.fetchone()
    assert row is not None
    return int(row[0])


def upsert_document(conn: sqlite3.Connection, fund_id: int, file_path: str, file_hash: str, doc_type: str, as_of_date: Optional[str], pages: int, parse_status: str, parse_confidence: float, extraction_method: str = "pattern") -> int:
    cur = conn.cursor()
    cur.execute(
        """
        INSERT OR IGNORE INTO fund_documents(fund_id, file_path, file_hash, doc_type, as_of_date, pages, ingested_at, parse_status, parse_confidence, extraction_method)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (fund_id, file_path, file_hash, doc_type, as_of_date, pages, datetime.utcnow().isoformat(), parse_status, parse_confidence, extraction_method),
    )
    conn.commit()
    cur.execute("SELECT id FROM fund_documents WHERE file_hash = ?", (file_hash,))
    row = cur.fetchone()
    assert row is not None
    return int(row[0])


def upsert_snapshot(conn: sqlite3.Connection, fund_id: int, as_of_date: Optional[str], metrics: Dict[str, Optional[float]], source_document_id: int) -> None:
    if not as_of_date:
        return
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO fund_performance_snapshots(fund_id, as_of_date, nav, unfunded, irr_net, tvpi, dpi, rvpi, pme, source_document_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
        ON CONFLICT(fund_id, as_of_date) DO UPDATE SET
            nav=excluded.nav,
            unfunded=excluded.unfunded,
            irr_net=excluded.irr_net,
            tvpi=excluded.tvpi,
            dpi=excluded.dpi,
            rvpi=excluded.rvpi,
            source_document_id=excluded.source_document_id
        """,
        (
            fund_id,
            as_of_date,
            metrics.get("nav"),
            metrics.get("unfunded"),
            metrics.get("irr_net"),
            metrics.get("tvpi"),
            metrics.get("dpi"),
            metrics.get("rvpi"),
            source_document_id,
        ),
    )
    conn.commit()


def upsert_cash_flows(conn: sqlite3.Connection, fund_id: int, flows: List[Tuple[str, float, str, str]], source_document_id: int) -> None:
    cur = conn.cursor()
    for flow_date, amount, flow_type, description in flows:
        row_hash = hashlib.sha256(f"{fund_id}|{flow_date}|{amount}|{flow_type}|{description}".encode("utf-8")).hexdigest()
        cur.execute(
            """
            INSERT OR IGNORE INTO fund_cash_flows(fund_id, flow_date, amount, flow_type, description, source_document_id, source_row_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (fund_id, flow_date, amount, flow_type, description, source_document_id, row_hash),
        )
    conn.commit()


def ingest_one(conn: sqlite3.Connection, file_path: str, extract_pages: Callable[[str], List[str]] = extract_text_pages, dry_run: bool = False) -> Dict[str, object]:
    logger.info(f"Starting ingestion of {file_path}")
    file_hash = sha256_file(file_path)
    cur = conn.cursor()
    cur.execute("SELECT id FROM fund_documents WHERE file_hash = ?", (file_hash,))
    if cur.fetchone() is not None:
        logger.info(f"Skipping duplicate file: {file_path}")
        return {
            "file": file_path,
            "skipped_duplicate": True,
            "parse_status": "skipped",
            "errors": [],
        }

    logger.info(f"Extracting text from {file_path}")
    pages = extract_pages(file_path)
    pages = pages or [""]
    logger.info(f"Extracted {len(pages)} pages, total chars: {sum(len(p) for p in pages)}")
    
    fund_name = detect_fund_name(pages)
    as_of_date = detect_as_of_date(pages)
    doc_type = classify_doc_type(pages)
    metrics = parse_metrics(pages)
    flows = parse_cash_flows(pages)
    
    logger.info(f"Pattern detection results: fund='{fund_name}', date='{as_of_date}', type='{doc_type}'")
    logger.info(f"Metrics found: {[k for k, v in metrics.items() if v is not None]}")
    logger.info(f"Cash flows detected: {len(flows)}")

    confidence = 0.6
    if metrics.get("nav") is not None or metrics.get("irr_net") is not None:
        confidence += 0.2
    if as_of_date:
        confidence += 0.1
    confidence = min(confidence, 0.95)
    
    logger.info(f"Confidence score: {confidence:.2f}")
    
    # Hybrid logic: try LLM if confidence is low
    LLM_FALLBACK_THRESHOLD = float(os.getenv('FUND_PDF_LLM_THRESHOLD', '0.70'))
    use_llm = os.getenv('FUND_PDF_USE_LLM', 'true').lower() == 'true'
    extraction_method = "pattern"
    
    if confidence < LLM_FALLBACK_THRESHOLD and use_llm:
        logger.info(f"Confidence {confidence:.2f} below threshold {LLM_FALLBACK_THRESHOLD}, trying LLM extraction")
        try:
            # Get LLM config from environment
            llm_provider = os.getenv('LLM_PROVIDER', 'ollama')
            llm_model = os.getenv('LLM_MODEL', 'phi4-mini:3.8b')
            ollama_url = os.getenv('OLLAMA_URL', 'http://localhost:11434')
            lmstudio_base_url = os.getenv('LMSTUDIO_BASE_URL', 'http://localhost:1234/v1')
            openai_api_key = os.getenv('OPENAI_API_KEY')
            azure_openai_endpoint = os.getenv('AZURE_OPENAI_ENDPOINT')
            azure_openai_api_key = os.getenv('AZURE_OPENAI_API_KEY')
            azure_openai_deployment = os.getenv('AZURE_OPENAI_DEPLOYMENT')
            
            llm_result = extract_with_llm(
                pages, llm_provider, llm_model, ollama_url, lmstudio_base_url,
                openai_api_key, azure_openai_endpoint, azure_openai_api_key, azure_openai_deployment
            )
            
            # Merge LLM results with pattern results (LLM takes precedence)
            if llm_result.get("fund_name") != "Unknown Fund":
                fund_name = llm_result["fund_name"]
            if llm_result.get("as_of_date"):
                as_of_date = llm_result["as_of_date"]
            if llm_result.get("doc_type") != "report":
                doc_type = llm_result["doc_type"]
            
            # Merge metrics (LLM overwrites pattern)
            for key, value in llm_result.get("metrics", {}).items():
                if value is not None:
                    metrics[key] = value
            
            # Add LLM cash flows
            llm_flows = llm_result.get("cash_flows", [])
            if llm_flows:
                flows.extend(llm_flows)
            
            # Use LLM confidence if higher
            llm_confidence = llm_result.get("confidence", 0.5)
            if llm_confidence > confidence:
                confidence = llm_confidence
                extraction_method = "llm"
            else:
                extraction_method = "hybrid"
            
            logger.info(f"LLM extraction completed: method={extraction_method}, final_confidence={confidence:.2f}")
            
        except Exception as e:
            logger.warning(f"LLM extraction failed, falling back to pattern results: {e}")
            extraction_method = "pattern_fallback"

    if dry_run:
        return {
            "file": file_path,
            "doc_type": doc_type,
            "fund_name": fund_name,
            "fund_slug": slugify(fund_name),
            "as_of_date": as_of_date,
            "metrics_found": {k: (v is not None) for k, v in metrics.items()},
            "flows_detected": len(flows),
            "parse_status": "dry_run",
            "parse_confidence": confidence,
            "errors": [],
        }

    fund_id = get_or_create_fund(conn, fund_name)
    doc_id = upsert_document(
        conn,
        fund_id,
        file_path=file_path,
        file_hash=file_hash,
        doc_type=doc_type,
        as_of_date=as_of_date,
        pages=len(pages),
        parse_status="parsed",
        parse_confidence=confidence,
        extraction_method=extraction_method,
    )

    upsert_snapshot(conn, fund_id, as_of_date, metrics, doc_id)
    if flows:
        upsert_cash_flows(conn, fund_id, flows, doc_id)
    return {
        "file": file_path,
        "doc_type": doc_type,
        "fund_name": fund_name,
        "fund_slug": slugify(fund_name),
        "as_of_date": as_of_date,
        "metrics_found": {k: (v is not None) for k, v in metrics.items()},
        "flows_detected": len(flows),
        "parse_status": "parsed",
        "parse_confidence": confidence,
        "extraction_method": extraction_method,
        "errors": [],
    }


def ingest_path_report(db_path: str, input_path: str, dry_run: bool = False, fail_fast: bool = False) -> Dict[str, object]:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    summary = {
        "funds_upserted": 0,
        "documents_ingested": 0,
        "snapshots_upserted": 0,  # best-effort; derived from details
        "cash_flows_upserted": 0,  # best-effort; derived from details
        "skipped_duplicates": 0,
        "errors": 0,
    }
    details: List[Dict[str, object]] = []
    try:
        ensure_schema(conn)
        for root, _dirs, files in os.walk(input_path):
            for name in files:
                if not name.lower().endswith(".pdf"):
                    continue
                full = os.path.join(root, name)
                try:
                    res = ingest_one(conn, full, extract_pages=extract_text_pages, dry_run=dry_run)
                    details.append(res)
                    if res.get("parse_status") == "skipped":
                        summary["skipped_duplicates"] += 1
                    elif res.get("parse_status") in ("parsed", "dry_run"):
                        summary["documents_ingested"] += 1
                        if res.get("parse_status") == "parsed":
                            # Rough increments; real counts would require DB diffs
                            summary["snapshots_upserted"] += 1 if res.get("as_of_date") else 0
                            summary["cash_flows_upserted"] += int(res.get("flows_detected", 0) or 0)
                except Exception as e:  # pragma: no cover
                    details.append({"file": full, "parse_status": "failed", "errors": [str(e)]})
                    summary["errors"] += 1
                    if fail_fast:
                        raise
    finally:
        conn.close()
    return {"summary": summary, "details": details}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest private fund PDFs into SQLite.")
    parser.add_argument("--path", default=os.getenv("FUND_PDF_DIR", "docs/fund_pdfs"), help="Folder containing PDF files")
    args = parser.parse_args(argv)

    db_path = os.getenv("DB_PATH", os.path.join("db", "transactions.db"))
    if not os.path.isdir(args.path):
        print(f"Input path not found: {args.path}", file=sys.stderr)
        return 1

    start = time.time()
    report = ingest_path_report(db_path=db_path, input_path=args.path)
    elapsed = time.time() - start
    print(f"Ingestion completed in {elapsed:.2f}s")
    print(report)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


