#!/bin/bash
cd "$(dirname "$0")"
if [ ! -d "venv" ]; then
  echo "⚙️  First run — setting up StreamFader..."
  python3 -m venv venv
  venv/bin/pip install -q -r requirements.txt
  echo "✅ Ready"
fi
pkill -f "streamfader/app.py" 2>/dev/null
echo "🎬 Starting StreamFader at http://localhost:5556"
venv/bin/python app.py
