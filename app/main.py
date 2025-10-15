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

# Configure logging
default_level = os.getenv('LOG_LEVEL', 'INFO')
logging.basicConfig(level=getattr(logging, default_level))
logger = logging.getLogger(__name__)

# Environment variables
qif_dir = os.getenv('QIF_DIR', '/qifs')
db_path = os.getenv('DB_PATH', '/db/transactions.db')
ollama_url = os.getenv('OLLAMA_URL')

# Create FastAPI app
app = FastAPI()

# Ensure database
indexer = QIFIndexer(qif_dir, db_path)
indexer.ensure_database()
logger.info(f"Database ready at {db_path}")

# Setup LLM + SQL chain
db_uri = f"sqlite:///{db_path}"
db = SQLDatabase.from_uri(db_uri)
llm = Ollama(model="phi4-mini:3.8b", base_url=ollama_url)
logger.info("SQLDatabase and LLM initialized")

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

    # Stronger prompt to encourage correct output
    prompt = (
        f"You are a SQLite SQL expert. Only return a valid SQLite SELECT statement for the question below, using this schema:\n"
        f"{schema}\n"
        f"Never use YEAR() or transaction_date. Use strftime('%Y', date) for filtering years. Table name is lowercase 'transactions'.\n"
        f"Do not add markdown or code fences. Do not explain anything, only return SQL.\n"
        f"Question: {user_question}\n"
        f"SQL:"
    )

    ollama_url = os.getenv('OLLAMA_URL', 'http://localhost:11434')
    model = "phi4-mini:3.8b"

    response = requests.post(
        f"{ollama_url}/api/generate",
        json={"model": model, "prompt": prompt},
        stream=True
    )
    if response.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Ollama error: {response.text}")

    # Accumulate the streamed 'response' fields
    sql = ""
    for line in response.iter_lines():
        if line:
            line_decoded = line.decode('utf-8')  # decode from bytes to string
            logger.debug(f"Raw line from LLM: {line_decoded}")
            try:
                obj = json.loads(line_decoded)
                sql += obj.get("response", "")
            except Exception as e:
                logger.warning(f"Failed to parse JSON: {e} | Line: {line_decoded}")
                continue

    # Remove code fences/markdown just in case
    logger.info(f"Raw SQL from LLM before cleanup: {sql}")
    sql = re.sub(r'```sql\\s*', '', sql, flags=re.IGNORECASE)
    sql = re.sub(r'```', '', sql)
    sql = sql.strip().strip(';')
    logger.debug(f"Raw SQL from LLM: {sql}")

    if not sql or not sql.lower().startswith("select"):
        raise HTTPException(status_code=500, detail=f"No valid SQL was generated by the LLM. SQL: {sql}")

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
    except Exception as e:
        logger.exception("SQL execution error")
        raise HTTPException(status_code=500, detail=f"SQL execution failed: {e}")
