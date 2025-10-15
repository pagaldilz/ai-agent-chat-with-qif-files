FROM python:3.12.2-slim
WORKDIR /ui
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["streamlit", "run", "qif_chat.py", "--server.port=8501", "--server.address=0.0.0.0"]
