#!/usr/bin/env bash
# Single-container mode: FastAPI on 127.0.0.1:8000 (internal), Streamlit on $PORT (public).
set -e
export API_URL="http://127.0.0.1:8000"
uvicorn app.main:app --host 127.0.0.1 --port 8000 &
exec streamlit run ui/streamlit_app.py --server.port "${PORT:-7860}" --server.address 0.0.0.0 \
     --server.headless true --browser.gatherUsageStats false
