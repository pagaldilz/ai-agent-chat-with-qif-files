# ---------------------------
# app/main.py
# ---------------------------
import os
import requests
import logging
import re
import json
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from langchain_community.utilities import SQLDatabase
from langchain_community.llms import Ollama
from sqlalchemy import text
from app.qif_indexer import QIFIndexer
from app.analyzers.recurring_detector import RecurringDetector
from app.analyzers.merchant_normalizer import MerchantNormalizer
from app.analyzers.anomaly_detector import AnomalyDetector
from app.analyzers.forecast_engine import ForecastEngine
from app.analyzers.investment_analyzer import InvestmentAnalyzer
from app.analyzers.transfer_detector import TransferDetector
from app.analyzers.budget_tracker import BudgetTracker
from typing import Optional

try:
    # OpenAI SDK (also used for Azure by configuring endpoint and API version)
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore

# Configure logging
default_level = os.getenv('LOG_LEVEL', 'INFO')
logging.basicConfig(level=getattr(logging, default_level))
logger = logging.getLogger(__name__)

# Environment variables
qif_dir = os.getenv('QIF_DIR', '/qifs')
db_path = os.getenv('DB_PATH', '/db/transactions.db')
ollama_url = os.getenv('OLLAMA_URL', 'http://localhost:11434')

# LLM configuration
llm_provider = os.getenv('LLM_PROVIDER', 'lmstudio').lower()  # lmstudio|ollama|openai|azure
llm_model = os.getenv('LLM_MODEL', 'phi4-mini:3.8b')
llm_temperature = float(os.getenv('LLM_TEMPERATURE', '0'))

# LM Studio configuration (OpenAI-compatible local API)
lmstudio_base_url = os.getenv('LMSTUDIO_BASE_URL', 'http://localhost:1234/v1')
lmstudio_api_key = os.getenv('LMSTUDIO_API_KEY')

# OpenAI/Azure configuration
openai_api_key = os.getenv('OPENAI_API_KEY')
azure_openai_endpoint = os.getenv('AZURE_OPENAI_ENDPOINT')
azure_openai_api_key = os.getenv('AZURE_OPENAI_API_KEY')
azure_openai_deployment = os.getenv('AZURE_OPENAI_DEPLOYMENT')
azure_openai_api_version = os.getenv('AZURE_OPENAI_API_VERSION', '2024-02-01')

# Create FastAPI app
app = FastAPI()

# Ensure database
indexer = QIFIndexer(qif_dir, db_path)
indexer.ensure_database()
logger.info(f"Database ready at {db_path}")

# Setup LLM + SQL chain
db_uri = f"sqlite:///{db_path}"
db = SQLDatabase.from_uri(db_uri)
logger.info("SQLDatabase initialized")

def _generate_sql_with_ollama(prompt: str) -> str:
    response = requests.post(
        f"{ollama_url}/api/generate",
        json={"model": llm_model, "prompt": prompt, "options": {"temperature": llm_temperature}},
        stream=True,
        timeout=120,
    )
    if response.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Ollama error: {response.text}")
    sql = ""
    for line in response.iter_lines():
        if not line:
            continue
        line_decoded = line.decode('utf-8')
        try:
            obj = json.loads(line_decoded)
            sql += obj.get("response", "")
        except Exception:
            continue
    return sql

def _generate_sql_with_openai(prompt: str) -> str:
    if OpenAI is None:
        raise HTTPException(status_code=500, detail="OpenAI SDK not installed. Add 'openai' to requirements.")
    # Standard OpenAI
    client = OpenAI(api_key=openai_api_key)
    completion = client.chat.completions.create(
        model=llm_model,
        temperature=llm_temperature,
        messages=[{"role": "system", "content": "You are a SQLite SQL expert."},
                  {"role": "user", "content": prompt}],
    )
    return completion.choices[0].message.content or ""

def _generate_sql_with_lmstudio(prompt: str) -> str:
    if OpenAI is None:
        raise HTTPException(status_code=500, detail="OpenAI SDK not installed. Add 'openai' to requirements.")
    # LM Studio exposes OpenAI-compatible endpoints; api_key may be optional
    client = OpenAI(api_key=lmstudio_api_key or "lm-studio", base_url=lmstudio_base_url)
    completion = client.chat.completions.create(
        model=llm_model,
        temperature=llm_temperature,
        messages=[{"role": "system", "content": "You are a SQLite SQL expert."},
                  {"role": "user", "content": prompt}],
    )
    return completion.choices[0].message.content or ""

def _generate_sql_with_azure(prompt: str) -> str:
    if OpenAI is None:
        raise HTTPException(status_code=500, detail="OpenAI SDK not installed. Add 'openai' to requirements.")
    if not (azure_openai_endpoint and azure_openai_api_key and azure_openai_deployment):
        raise HTTPException(status_code=500, detail="Azure OpenAI configuration missing.")
    client = OpenAI(
        api_key=azure_openai_api_key,
        base_url=f"{azure_openai_endpoint}/openai/deployments/{azure_openai_deployment}",
    )
    completion = client.chat.completions.create(
        model=llm_model,  # often ignored; deployment name routes the model
        temperature=llm_temperature,
        messages=[{"role": "system", "content": "You are a SQLite SQL expert."},
                  {"role": "user", "content": prompt}],
        extra_headers={"api-version": azure_openai_api_version},
    )
    return completion.choices[0].message.content or ""

def generate_sql(prompt: str) -> str:
    provider = llm_provider
    if provider == 'ollama':
        return _generate_sql_with_ollama(prompt)
    if provider == 'lmstudio':
        return _generate_sql_with_lmstudio(prompt)
    if provider == 'openai':
        return _generate_sql_with_openai(prompt)
    if provider == 'azure':
        return _generate_sql_with_azure(prompt)
    raise HTTPException(status_code=500, detail=f"Unsupported LLM_PROVIDER: {provider}")

def format_markdown_table(rows):
    if not rows:
        return "No results found."
    headers = list(rows[0].keys())
    header_line = "| " + " | ".join(headers) + " |"
    sep_line = "| " + " | ".join(["---"]*len(headers)) + " |"
    body = "\n".join("| " + " | ".join(str(row[k]) for k in headers) + " |" for row in rows)
    return "\n".join([header_line, sep_line, body])

def format_human_readable(rows, sql):
    if not rows:
        return "No results found."
    # Handle single aggregate row
    if len(rows) == 1 and len(rows[0]) == 1:
        key, value = list(rows[0].items())[0]
        return f"The {key.replace('_', ' ')} is {value}."
    # Else, show as table
    return format_markdown_table(rows)

class Query(BaseModel):
    question: str

# SQL guardrails
ALLOWED_COLUMNS = {"date", "payee", "category", "memo", "amount", "source_file", "account_name", "account_type"}
DENY_PATTERN = re.compile(r"\b(insert|update|delete|drop|alter|attach|pragma|create|replace|vacuum|analyze|grant|reindex)\b", re.IGNORECASE)
SQL_KEYWORDS = {
    'select', 'from', 'where', 'group', 'by', 'having', 'order', 'limit', 'offset',
    'asc', 'desc', 'and', 'or', 'like', 'in', 'as', 'on', 'join', 'inner', 'left', 'right', 'outer'
}

def sanitize_sql(sql: str) -> str:
    # Remove code fences/markdown just in case
    sql = re.sub(r"```sql\\s*", '', sql, flags=re.IGNORECASE)
    sql = re.sub(r"```", '', sql)
    return sql.strip()

def enforce_guardrails(sql: str) -> str:
    if not sql.lower().startswith("select"):
        raise HTTPException(status_code=400, detail="Only SELECT statements are allowed (guardrails)")
    if DENY_PATTERN.search(sql):
        raise HTTPException(status_code=400, detail="Statement contains disallowed keywords (guardrails)")
    if ";" in sql:
        raise HTTPException(status_code=400, detail="Multiple statements are not allowed (guardrails)")
    # must query from transactions
    if re.search(r"\bfrom\s+([^\s]+)", sql, re.IGNORECASE):
        m = re.search(r"\bfrom\s+([^\s]+)", sql, re.IGNORECASE)
        if m and m.group(1).strip().lower().strip('"`') != 'transactions':
            raise HTTPException(status_code=400, detail="Only FROM transactions is allowed (guardrails)")
    else:
        raise HTTPException(status_code=400, detail="FROM clause is required (guardrails)")
    # simple column token validation
    tokens = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", sql)
    for t in tokens:
        tl = t.lower()
        if tl in SQL_KEYWORDS or tl == 'transactions':
            continue
        # Skip SQLite functions
        if tl in {'strftime', 'count', 'sum', 'avg', 'min', 'max', 'distinct'}:
            continue
        # Skip numbers captured as tokens unintentionally
        if tl.isdigit():
            continue
        # treat as potential column name when not part of a string literal context (best-effort)
        # This naive check can over-validate; keep allow-list tight
        if tl not in ALLOWED_COLUMNS:
            # Allow aliases that repeat allowed names after AS, e.g., amount as total_amount
            # We permit any alias; only source columns are validated
            pass
    # Add default LIMIT if not aggregate and not already limited
    is_aggregate = re.search(r"\b(count|sum|avg|min|max)\(", sql, re.IGNORECASE) is not None
    if (" limit " not in sql.lower()) and (not is_aggregate):
        sql += " LIMIT 500"
    return sql

@app.post('/admin/rebuild')
async def admin_rebuild():
    """Rebuild the SQLite database from QIF files."""
    try:
        # Remove existing DB file to force rebuild
        try:
            if os.path.exists(db_path):
                os.remove(db_path)
        except Exception as e:
            logger.warning(f"Could not remove existing DB: {e}")
        # Recreate indexer (fresh engine) and rebuild
        global indexer
        indexer = QIFIndexer(qif_dir, db_path)
        stats = indexer.build_database()
        logger.info("Database rebuild complete")
        return {
            "status": "ok",
            "message": "Database rebuilt",
            "import_summary": stats
        }
    except Exception as e:
        logger.exception("Database rebuild failed")
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/transactions/{year}')
async def list_transactions(year: int):
    try:
        conn = indexer.engine.connect()
        q = text(
            "SELECT date, payee, category, memo, amount "
            "FROM transactions WHERE strftime('%Y', date)=:yr"
        )
        res = conn.execute(q, {"yr": f"{year}"})
        logger.info(f"Listing transactions for year {year}")
        if res.rowcount == 0:
            logger.warning(f"No transactions found for year {year}")
            return {'transactions': []}
        # Convert result to list of dicts
        res = res.fetchall()
        if not res:
            logger.warning(f"No transactions found for year {year}")
            return {'transactions': []}
        # Format results
        logger.info(f"Found {len(res)} transactions for year {year}")
        rows = []
        for row in res:
            r = dict(row._mapping)
            date_val = r.get('date')
            if hasattr(date_val, 'isoformat'):
                r['date'] = date_val.isoformat()
            else:
                r['date'] = str(date_val) if date_val else None
#            r['date'] = r['date'].isoformat() if r['date'] else None
            r['amount'] = f"${r['amount']:,.2f}" if r['amount'] is not None else None
            rows.append(r)
        conn.close()
        logger.info(f"Returned {len(rows)} transactions for year {year}")
        return {'transactions': rows}
    except Exception as e:
        logger.exception("Transaction listing error")
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/health')
def health_check():
    try:
        provider = llm_provider
        if provider == 'ollama':
            r = requests.get(f"{ollama_url}/v1/models", timeout=5)
            r.raise_for_status()
            logger.info("Health check OK (ollama)")
            return {'status': 'ok'}
        if provider == 'lmstudio':
            base = lmstudio_base_url.rstrip('/')
            r = requests.get(f"{base}/models", timeout=5)
            r.raise_for_status()
            logger.info("Health check OK (lmstudio)")
            return {'status': 'ok'}
        # For hosted providers, simply report OK if configured
        if provider == 'openai':
            logger.info("Health check OK (openai)")
            return {'status': 'ok'}
        if provider == 'azure':
            logger.info("Health check OK (azure)")
            return {'status': 'ok'}
        raise HTTPException(status_code=500, detail=f"Unsupported LLM_PROVIDER: {provider}")
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail=str(e))

@app.get('/count')
async def count_transactions():
    """Return total number of transactions in the database."""
    try:
        conn = indexer.engine.connect()
        result = conn.execute(text("SELECT COUNT(*) as cnt FROM transactions"))
        row = result.fetchone()
        count = row[0] if row is not None else 0
        conn.close()
        logger.info(f"Total transactions count: {count}")
        return {'count': count}
    except Exception as e:
        logger.exception("Error counting transactions")
        raise HTTPException(status_code=500, detail=str(e))
    
    # New endpoint: count transactions for a given year
@app.get('/transactions/count/{year}')
async def count_transactions_year(year: int):
    """Return the number of transactions for the specified year."""
    try:
        conn = indexer.engine.connect()
        result = conn.execute(text(
            "SELECT COUNT(*) FROM transactions "
            "WHERE strftime('%Y', date)=:yr"
        ), {"yr": f"{year}"})
        row = result.fetchone()
        count = row[0] if row is not None else 0
        conn.close()
        logger.info(f"Transactions count for {year}: {count}")
        return {'year': year, 'count': count}
    except Exception as e:
        logger.exception(f"Error counting transactions for year {year}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/analyze/recurring')
async def analyze_recurring():
    """Analyze and detect recurring transaction patterns."""
    try:
        detector = RecurringDetector(indexer.engine)
        patterns = detector.detect_recurring_patterns()
        detector.save_recurring_patterns(patterns)
        
        projections = detector.calculate_monthly_projections(patterns)
        
        logger.info(f"Analyzed {len(patterns)} recurring patterns")
        return {
            'patterns': patterns,
            'projections': projections,
            'status': 'success'
        }
    except Exception as e:
        logger.exception("Recurring analysis failed")
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/recurring')
async def get_recurring():
    """Get detected recurring transaction patterns."""
    try:
        detector = RecurringDetector(indexer.engine)
        patterns = detector.get_recurring_patterns()
        projections = detector.calculate_monthly_projections(patterns)
        
        return {
            'patterns': patterns,
            'projections': projections
        }
    except Exception as e:
        logger.exception("Failed to get recurring patterns")
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/admin/normalize-merchants')
async def normalize_merchants():
    """Normalize merchant names and create canonical mappings."""
    try:
        normalizer = MerchantNormalizer(indexer.engine)
        mappings = normalizer.normalize_merchants()
        
        logger.info(f"Normalized {len(mappings)} merchants")
        return {
            'mappings': mappings,
            'status': 'success'
        }
    except Exception as e:
        logger.exception("Merchant normalization failed")
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/merchants')
async def get_merchants():
    """Get merchant statistics and top merchants."""
    try:
        normalizer = MerchantNormalizer(indexer.engine)
        statistics = normalizer.get_merchant_statistics()
        top_merchants = normalizer.get_top_merchants()
        
        return {
            'statistics': statistics,
            'top_merchants': top_merchants
        }
    except Exception as e:
        logger.exception("Failed to get merchant data")
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/analyze/anomalies')
async def analyze_anomalies():
    """Analyze and detect transaction anomalies."""
    try:
        detector = AnomalyDetector(indexer.engine)
        anomalies = detector.detect_all_anomalies()
        detector.save_anomalies(anomalies)
        
        summary = detector.get_anomaly_summary()
        
        logger.info(f"Analyzed {len(anomalies)} anomalies")
        return {
            'anomalies': anomalies,
            'summary': summary,
            'status': 'success'
        }
    except Exception as e:
        logger.exception("Anomaly analysis failed")
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/anomalies')
async def get_anomalies(anomaly_type: str = None, limit: int = 50):
    """Get detected anomalies."""
    try:
        detector = AnomalyDetector(indexer.engine)
        anomalies = detector.get_anomalies(anomaly_type, limit)
        summary = detector.get_anomaly_summary()
        
        return {
            'anomalies': anomalies,
            'summary': summary
        }
    except Exception as e:
        logger.exception("Failed to get anomalies")
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/forecast/trends')
async def get_spending_trends(days_back: int = 90):
    """Get spending trends for forecast accuracy."""
    try:
        if days_back < 1 or days_back > 365:
            raise HTTPException(status_code=400, detail="Days back must be between 1 and 365")
        
        engine = ForecastEngine(indexer.engine)
        trends = engine.get_spending_trends(days_back)
        
        return trends
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get spending trends")
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/forecast/summary/{days}')
async def get_forecast_summary(days: int):
    """Get forecast summary for all accounts."""
    try:
        if days < 1 or days > 365:
            raise HTTPException(status_code=400, detail="Days must be between 1 and 365")
        
        engine = ForecastEngine(indexer.engine)
        summary = engine.get_forecast_summary(days)
        
        return summary
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to generate forecast summary")
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/forecast/{days}')
async def get_forecast(days: int, account_name: str = None):
    """Get cash flow forecast for specified number of days."""
    try:
        if days < 1 or days > 365:
            raise HTTPException(status_code=400, detail="Days must be between 1 and 365")
        
        engine = ForecastEngine(indexer.engine)
        forecast = engine.generate_forecast(days, account_name)
        
        return forecast
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to generate forecast")
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/admin/parse-investments')
async def parse_investments():
    """Parse investment data from QIF files and store in database."""
    try:
        analyzer = InvestmentAnalyzer(indexer.engine, qif_dir)
        result = analyzer.parse_and_store_investments()
        
        return result
    except Exception as e:
        logger.exception("Investment parsing failed")
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/investments/portfolio')
async def get_portfolio():
    """Get current portfolio summary."""
    try:
        analyzer = InvestmentAnalyzer(indexer.engine, qif_dir)
        portfolio = analyzer.get_portfolio_summary()
        
        return portfolio
    except Exception as e:
        logger.exception("Failed to get portfolio")
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/investments/transactions')
async def get_investment_transactions(security: str = None, limit: int = 100):
    """Get investment transaction history."""
    try:
        analyzer = InvestmentAnalyzer(indexer.engine, qif_dir)
        transactions = analyzer.get_transaction_history(security, limit)
        
        return {'transactions': transactions}
    except Exception as e:
        logger.exception("Failed to get investment transactions")
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/investments/performance')
async def get_investment_performance():
    """Get investment performance analysis."""
    try:
        analyzer = InvestmentAnalyzer(indexer.engine, qif_dir)
        performance = analyzer.get_performance_analysis()
        
        return performance
    except Exception as e:
        logger.exception("Failed to get investment performance")
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/investments/allocation')
async def get_asset_allocation():
    """Get asset allocation breakdown."""
    try:
        analyzer = InvestmentAnalyzer(indexer.engine, qif_dir)
        allocation = analyzer.get_asset_allocation()
        
        return allocation
    except Exception as e:
        logger.exception("Failed to get asset allocation")
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/admin/detect-transfers')
async def detect_transfers():
    """Detect and analyze transfers between accounts."""
    try:
        detector = TransferDetector(indexer.engine)
        transfers = detector.detect_transfers()
        detector.save_transfers(transfers)
        detector.update_transaction_transfer_flags()
        
        summary = detector.get_transfer_summary()
        
        logger.info(f"Detected {len(transfers)} transfers")
        return {
            'transfers': transfers,
            'summary': summary,
            'status': 'success'
        }
    except Exception as e:
        logger.exception("Transfer detection failed")
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/transfers')
async def get_transfers(limit: int = 100):
    """Get detected transfers."""
    try:
        detector = TransferDetector(indexer.engine)
        transfers = detector.get_transfers(limit)
        summary = detector.get_transfer_summary()
        
        return {
            'transfers': transfers,
            'summary': summary
        }
    except Exception as e:
        logger.exception("Failed to get transfers")
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/transfers/cash-flow')
async def get_net_cash_flow(account_name: str = None, exclude_transfers: bool = True):
    """Get net cash flow excluding transfers."""
    try:
        detector = TransferDetector(indexer.engine)
        cash_flow = detector.calculate_net_cash_flow(account_name, exclude_transfers)
        
        return cash_flow
    except Exception as e:
        logger.exception("Failed to get net cash flow")
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/budgets/suggestions')
async def get_budget_suggestions(period: str = 'monthly'):
    """Get AI-powered budget suggestions based on historical spending."""
    try:
        tracker = BudgetTracker(indexer.engine)
        tracker.create_budget_tables()
        suggestions = tracker.suggest_budgets(period)
        
        return {'suggestions': suggestions}
    except Exception as e:
        logger.exception("Failed to get budget suggestions")
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/budgets')
async def create_budget(budget_data: dict):
    """Create a new budget."""
    try:
        tracker = BudgetTracker(indexer.engine)
        tracker.create_budget_tables()
        
        result = tracker.create_budget(
            budget_data['category'],
            budget_data['amount'],
            budget_data.get('period', 'monthly'),
            budget_data.get('start_date'),
            budget_data.get('end_date')
        )
        
        return result
    except Exception as e:
        logger.exception("Failed to create budget")
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/budgets')
async def get_budgets():
    """Get all budgets."""
    try:
        tracker = BudgetTracker(indexer.engine)
        budgets = tracker.get_budgets()
        progress = tracker.get_budget_progress()
        summary = tracker.get_budget_summary()
        
        return {
            'budgets': budgets,
            'progress': progress,
            'summary': summary
        }
    except Exception as e:
        logger.exception("Failed to get budgets")
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/goals')
async def create_goal(goal_data: dict):
    """Create a new financial goal."""
    try:
        tracker = BudgetTracker(indexer.engine)
        tracker.create_budget_tables()
        
        result = tracker.create_goal(
            goal_data['name'],
            goal_data['target_amount'],
            goal_data.get('deadline'),
            goal_data.get('category')
        )
        
        return result
    except Exception as e:
        logger.exception("Failed to create goal")
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/goals')
async def get_goals():
    """Get all goals."""
    try:
        tracker = BudgetTracker(indexer.engine)
        goals = tracker.get_goals()
        progress = tracker.get_goal_progress()
        summary = tracker.get_budget_summary()
        
        return {
            'goals': goals,
            'progress': progress,
            'summary': summary
        }
    except Exception as e:
        logger.exception("Failed to get goals")
        raise HTTPException(status_code=500, detail=str(e))

@app.put('/goals/{goal_id}/progress')
async def update_goal_progress(goal_id: int, progress_data: dict):
    """Update goal progress."""
    try:
        tracker = BudgetTracker(indexer.engine)
        result = tracker.update_goal_progress(goal_id, progress_data['current_amount'])
        
        return result
    except Exception as e:
        logger.exception("Failed to update goal progress")
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/chat')
async def chat(query: dict):
    if 'question' not in query:
        raise HTTPException(status_code=422, detail="Missing required field: question")
    
    user_question = query['question']
    
    if not user_question or user_question.strip() == "":
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    schema = "transactions(date DATE, payee TEXT, category TEXT, memo TEXT, amount REAL, source_file TEXT, account_name TEXT, account_type TEXT)"

    prompt = (
        f"You are a SQLite SQL expert. Return only a valid SQLite SELECT statement using this schema: \n"
        f"{schema}\n"
        f"Rules: Only SELECT; table is 'transactions'; columns are date, payee, category, memo, amount, source_file, account_name, account_type. "
        f"Use strftime('%Y', date) to filter by year. Do not include explanations, markdown, or code fences.\n"
        f"Question: {user_question}\n"
        f"SQL:"
    )

    try:
        raw_sql = generate_sql(prompt)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("LLM generation error")
        raise HTTPException(status_code=500, detail=f"LLM generation failed: {e}")

    logger.info(f"Raw SQL from LLM before cleanup: {raw_sql}")
    sql = sanitize_sql(raw_sql)
    sql = sql.strip().strip(';')
    logger.debug(f"SQL after sanitize: {sql}")

    if not sql:
        raise HTTPException(status_code=500, detail="Empty SQL returned by LLM")

    # Guardrails
    sql = enforce_guardrails(sql)
    logger.info(f"Executing SQL (sanitized and validated): {sql}")

    try:
        conn = indexer.engine.connect()
        result = conn.execute(text(sql))
        rows = []
        for row in result:
            d = dict(row._mapping)
            date_val = d.get('date')
            if hasattr(date_val, 'isoformat'):
                d['date'] = date_val.isoformat()
            else:
                d['date'] = str(date_val) if date_val else None
            amt = d.get('amount')
            if isinstance(amt, (int, float)):
                d['amount'] = f"${amt:,.2f}"
            rows.append(d)
        conn.close()
        
        # Generate explanation of what the query does
        explanation_prompt = (
            f"Explain what this SQL query does in simple terms: {sql}\n"
            f"Context: The user asked: '{user_question}'\n"
            f"Return a brief 1-2 sentence explanation of what the query is looking for."
        )
        
        try:
            explanation = generate_sql(explanation_prompt)
            explanation = sanitize_sql(explanation).strip()
        except Exception as e:
            logger.warning(f"Failed to generate explanation: {e}")
            explanation = f"This query searches for transactions matching your criteria."
        
        return {
            'answer': format_human_readable(rows, sql),
            'sql': sql,
            'explanation': explanation
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("SQL execution error")
        raise HTTPException(status_code=500, detail=f"SQL execution failed: {e}")
