"""
Ormodex ERP - Main FastAPI entry point (Render/any PaaS or local uvicorn).
Re-exports `app` from `server.py` so both of these work:
    uvicorn main:app --host 0.0.0.0 --port $PORT
    gunicorn -k uvicorn.workers.UvicornWorker main:app --bind 0.0.0.0:$PORT
"""
import os
import uvicorn
from server import app

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run("main:app", host=host, port=port, reload=False)
