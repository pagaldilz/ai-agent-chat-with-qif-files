# QIF Agent

**QIF Agent** is an AI-powered financial assistant that lets you chat with your own QIF (Quicken Interchange Format) data. It parses your QIF files, stores transactions in a SQLite database, and uses an LLM (via [Ollama](https://ollama.com/)) to answer natural language questions about your finances. The project includes a FastAPI backend and a Streamlit-based web UI.

Start the Streamlib web UI, then ask it queries like
- List all transactions from 2021 where category like Util or like Electric
- What the sum total for all of 2018 where the category like Dues?

The Agent creates a SQLite database called **"transactions.db"**.  A table **"transactions"** is created and has the following fields:
- date
- payee
- category
- memo
- amount


## Features

- **QIF Parsing:** Indexes and parses QIF files into a structured SQLite database.
- **Natural Language Chat:** Ask questions about your transactions, totals, trends, and more.
- **Web UI:** Simple chat interface built with Streamlit.
- **Dockerized:** Easy to run with Docker Compose.

## Project Structure

```
.
├── app/                # Backend FastAPI app and QIF indexer
│   ├── main.py
│   └── qif_indexer.py
├── db/                 # SQLite database storage (created at runtime)
│   └── transactions.db
├── qifs/               # Place your QIF files here
│   └── pb2024.qif
├── ui/                 # Streamlit UI
│   ├── qif_chat.py
│   ├── requirements.txt
│   └── Dockerfile
├── requirements.txt    # Backend Python dependencies
├── Dockerfile          # Backend Dockerfile
├── docker-compose.yml  # Multi-service orchestration
└── .gitignore
```

## Prerequisites

- [Docker](https://www.docker.com/) and [Docker Compose](https://docs.docker.com/compose/)
- [Ollama](https://ollama.com/) running locally or accessible (for LLM inference)
- At least one `.qif` file in the `qifs/` directory

## Quick Start

1. **Start Ollama**

   Make sure Ollama is running and the `phi4-mini:3.8b` model is available:

   ```sh
   ollama run phi4-mini:3.8b
   ```

2. **Add Your QIF Files**

   Place your `.qif` files in the `qifs/` directory.

3. **Build and Run with Docker Compose**

   ```sh
   docker-compose up --build
   ```

   - The FastAPI backend will be available at [http://localhost:8000](http://localhost:8000)
   - The Streamlit UI will be available at [http://localhost:8501](http://localhost:8501)

4. **Chat with Your QIF Agent**

   Open [http://localhost:8501](http://localhost:8501) in your browser and start asking questions about your finances!

## API Endpoints

- `POST /chat` — Ask a question about your transactions (used by the UI)
- `GET /transactions/{year}` — List transactions for a given year
- `GET /transactions/count/{year}` — Count transactions for a given year
- `GET /count` — Total number of transactions
- `GET /health` — Health check

## Environment Variables

Set in `docker-compose.yml`:

- `QIF_DIR` — Path to QIF files (default: `/qifs`)
- `DB_PATH` — Path to SQLite database (default: `/db/transactions.db`)
- `OLLAMA_URL` — URL for Ollama server (default: `http://host.docker.internal:11434`)

## Development

- Backend code: [`app/main.py`](app/main.py), [`app/qif_indexer.py`](app/qif_indexer.py)
- UI code: [`ui/qif_chat.py`](ui/qif_chat.py)

## License

MIT License. See [LICENSE](LICENSE) if present.

---

*Built with FastAPI, Streamlit, LangChain, and Ollama running LLM Ph4-mini:3.8b.*