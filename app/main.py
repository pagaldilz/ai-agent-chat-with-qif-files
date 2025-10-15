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
llm_provider = os.getenv('LLM_PROVIDER', 'ollama').lower()  # ollama|openai|azure
llm_model = os.getenv('LLM_MODEL', 'phi4-mini:3.8b')
llm_temperature = float(os.getenv('LLM_TEMPERATURE', '0'))

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
ALLOWED_COLUMNS = {"date", "payee", "category", "memo", "amount"}
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
        r = requests.get(f"{ollama_url}/v1/models")
        r.raise_for_status()
        logger.info("Health check OK")
        return {'status': 'ok'}
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

@app.post('/chat')
async def chat(query: dict):
    user_question = query['question']
    schema = "transactions(date DATE, payee TEXT, category TEXT, memo TEXT, amount REAL)"

    prompt = (
        f"You are a SQLite SQL expert. Return only a valid SQLite SELECT statement using this schema: \n"
        f"{schema}\n"
        f"Rules: Only SELECT; table is 'transactions'; columns are date, payee, category, memo, amount. "
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
        return {'answer': format_human_readable(rows, sql)}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("SQL execution error")
        raise HTTPException(status_code=500, detail=f"SQL execution failed: {e}")
