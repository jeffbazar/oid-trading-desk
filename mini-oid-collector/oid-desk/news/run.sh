#!/bin/bash
# com.oid.desk.news launcher: FinBERT venv if it imports cleanly, else the collector venv (aiohttp) + lexicon.
cd "$HOME/oid-desk/news"
FB="$HOME/oid-desk/news/venv-finbert/bin/python"
if [ -x "$FB" ] && "$FB" -c "import aiohttp, torch, transformers" >/dev/null 2>&1; then
  exec "$FB" news_stream.py
fi
export OID_NEWS_FINBERT=0
exec "$HOME/oid-quote/venv/bin/python" news_stream.py
