FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget gnupg unzip curl ca-certificates jq \
    tesseract-ocr tesseract-ocr-por poppler-utils \
    gcc g++ make \
    && rm -rf /var/lib/apt/lists/*

# Install Chrome
RUN mkdir -p /etc/apt/keyrings && \
    wget -qO- https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /etc/apt/keyrings/google-chrome.gpg && \
    echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update && apt-get install -y google-chrome-stable && \
    rm -rf /var/lib/apt/lists/*

# Install ChromeDriver (simplified - no version check needed)
RUN DRIVER_URL=$(wget -qO- https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json | jq -r ".channels.Stable.downloads.chromedriver[] | select(.platform==\"linux64\") | .url") && \
    wget -q $DRIVER_URL -O chromedriver.zip && \
    unzip chromedriver.zip && \
    mv chromedriver-linux64/chromedriver /usr/local/bin/chromedriver && \
    chmod +x /usr/local/bin/chromedriver && \
    rm -rf chromedriver.zip chromedriver-linux64

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create directories
RUN mkdir -p data/downloads/processos data/outputs data/extractions data/temp_doweb

# Copy test PDF if exists
#RUN if [ -f data/downloads/processos/TURCAP202500477.pdf ]; then cp data/downloads/processos/TURCAP202500477.pdf /app/data/downloads/processos/; fi

# Create sample CSV
RUN python3 -c "from pathlib import Path; csv = Path('data/outputs/analysis_summary.csv'); csv.parent.mkdir(parents=True, exist_ok=True); csv.write_text('ID,Empresa,Total Contratado,Processo,Link Documento\n00.000.000/0001-01,EMPRESA TESTE,R$ 100.000,TURCAP202500477,https://test.com\n') if not csv.exists() else None"

# Environment
ENV PYTHONUNBUFFERED=1
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_SERVER_HEADLESS=true
ENV CHROME_BIN=/usr/bin/google-chrome
ENV CHROMEDRIVER_PATH=/usr/local/bin/chromedriver

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 CMD curl -f http://localhost:8080/_stcore/health || exit 1

# Run Streamlit
CMD streamlit run app.py --server.port=$PORT --server.address=0.0.0.0