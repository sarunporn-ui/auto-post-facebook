#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

echo "==> Creating virtual environment (.venv)"
python3 -m venv .venv
source .venv/bin/activate

echo "==> Installing Python dependencies"
pip install --upgrade pip
pip install -r requirements.txt

if [ ! -f .env ]; then
  echo "==> Creating .env from .env.example (fill in your API keys before running)"
  cp .env.example .env
fi

mkdir -p data/generated

echo ""
echo "Setup complete."
echo ""
echo "Next steps:"
echo "  1. Edit .env and target_persona.json with your API keys and persona."
echo "  2. Start the API server:  source .venv/bin/activate && uvicorn src.main:app --reload"
echo "  3. Open the dashboard:    http://localhost:8000/dashboard"
echo "  (Optional) Prefer approving from your phone? Fill in the TELEGRAM_* keys and run:"
echo "     source .venv/bin/activate && python -m src.approval.telegram_bot"
echo ""
echo "macOS note: WeasyPrint (PDF generation) needs system libraries:"
echo "  brew install pango cairo gdk-pixbuf libffi"
