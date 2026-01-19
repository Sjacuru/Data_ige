# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    # Chrome dependencies
    wget \
    gnupg \
    unzip \
    curl \
    # Tesseract OCR
    tesseract-ocr \
    tesseract-ocr-por \
    # Poppler for PDF processing
    poppler-utils \
    # Build tools
    gcc \
    g++ \
    make \
    # Cleanup
    && rm -rf /var/lib/apt/lists/*

# Install Chrome (modern fix - no apt-key)
RUN apt-get update && \
    apt-get install -y gnupg wget ca-certificates && \
    mkdir -p /etc/apt/keyrings && \
    wget -qO- https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /etc/apt/keyrings/google-chrome.gpg && \
    echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update && \
    apt-get install -y google-chrome-stable && \
    rm -rf /var/lib/apt/lists/* /etc/apt/keyrings/google-chrome.gpg

# Install Chromium
RUN apt-get update && apt-get install -y \
    chromium \
    wget \
    unzip \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Get Chromium version and download matching ChromeDriver

# Install Chromium + deps
RUN apt-get update && apt-get install -y \
    chromium \
    wget \
    unzip \
    ca-certificates \
    jq \
    && rm -rf /var/lib/apt/lists/*

# Download matching ChromeDriver (Chrome 115+ compatible)
RUN CHROME_VERSION=$(chromium --version | grep -oP '\d+') && \
    DRIVER_URL=$(wget -qO- https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json \
      | jq -r ".channels.Stable.downloads.chromedriver[] | select(.platform==\"linux64\") | .url") && \
    wget -q $DRIVER_URL -O chromedriver.zip && \
    unzip chromedriver.zip && \
    mv chromedriver-linux64/chromedriver /usr/local/bin/chromedriver && \
    chmod +x /usr/local/bin/chromedriver && \
    rm -rf chromedriver.zip chromedriver-linux64

# Copy requirements first (for better caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p data/downloads data/downloads/processos data/outputs data/extractions data/temp_doweb data/temp_downloads

# ═══════════════════════════════════════════════════════════════
# NEW: Copy sample PDFs to container
# ═══════════════════════════════════════════════════════════════
# Copy sample PDFs from your local machine to the container
COPY data/downloads/processos/TURCAP202500477.pdf data/downloads/processos/ 2>/dev/null || true

# Copy sample CSV if exists
COPY data/outputs/analysis_summary.csv data/outputs/ 2>/dev/null || true

# ═══════════════════════════════════════════════════════════════
# NEW: Create a sample data generator script
# ═══════════════════════════════════════════════════════════════
RUN echo '#!/usr/bin/env python3\n\
import os\n\
import csv\n\
from pathlib import Path\n\
\n\
def create_sample_csv():\n\
    """Create sample CSV if none exists"""\n\
    csv_file = Path("data/outputs/analysis_summary.csv")\n\
    \n\
    if csv_file.exists():\n\
        print("CSV already exists, skipping...")\n\
        return\n\
    \n\
    # Get PDFs in processos folder\n\
    processos_dir = Path("data/downloads/processos")\n\
    pdf_files = list(processos_dir.glob("*.pdf"))\n\
    \n\
    if not pdf_files:\n\
        print("No PDF files found, creating empty CSV...")\n\
        return\n\
    \n\
    print(f"Creating CSV with {len(pdf_files)} sample entries...")\n\
    \n\
    with open(csv_file, "w", newline="", encoding="utf-8") as f:\n\
        writer = csv.writer(f)\n\
        writer.writerow(["ID", "Empresa", "Total Contratado", "Processo", "Link Documento"])\n\
        \n\
        for i, pdf in enumerate(pdf_files[:10], 1):\n\
            # Extract processo from filename if possible\n\
            filename = pdf.stem\n\
            writer.writerow([\n\
                f"00.000.000/0001-{i:02d}",\n\
                f"EMPRESA EXEMPLO {i}",\n\
                "R$ 100.000,00",\n\
                filename,\n\
                f"https://acesso.processo.rio/sigaex/public/app/transparencia/processo?n={filename}"\n\
            ])\n\
    \n\
    print(f"Created: {csv_file}")\n\
\n\
if __name__ == "__main__":\n\
    create_sample_csv()\n\
' > /app/create_sample_data.py && chmod +x /app/create_sample_data.py

# Run sample data creator on container start
RUN python3 /app/create_sample_data.py

# Set environment variables
ENV PYTHONUNBUFFERED=1
#ENV STREAMLIT_SERVER_PORT=8501 # ChatGPT told me to remove this line 
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_SERVER_HEADLESS=true
ENV CHROME_BIN=/usr/bin/google-chrome
ENV CHROMEDRIVER_PATH=/usr/local/bin/chromedriver

# Expose Streamlit port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:$PORT/_stcore/health || exit 1


# Run Streamlit
CMD streamlit run app.py --server.port=$PORT --server.address=0.0.0.0