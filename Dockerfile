FROM python:3.12.2-slim

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Install test dependencies (for running pytest inside the container)
COPY tests/requirements.txt ./tests-requirements.txt
RUN pip install --no-cache-dir -r tests-requirements.txt || true

COPY app/ ./app
COPY pytest.ini ./pytest.ini
COPY tests/ ./tests
COPY test_db_schema.py ./test_db_schema.py

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]