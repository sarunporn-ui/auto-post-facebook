FROM python:3.13-slim

# WeasyPrint runtime libs (Format 4 PDF) + Thai fonts for correct PDF rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
      libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 \
      libcairo2 libffi8 libjpeg62-turbo shared-mime-info \
      fonts-thai-tlwg fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
# Railway/Render inject $PORT; default to 8000 locally.
CMD ["sh", "-c", "uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
