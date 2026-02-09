FROM python:3.11-slim

WORKDIR /app

# Install system dependencies if needed (e.g. for pdfplumber dependencies)
# pdfplumber/pdfminer usually works pure python, but just in case
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Expose port
EXPOSE 8000

# Command to run (same as main.py but explicit)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
