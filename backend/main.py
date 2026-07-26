"""
Ormodex ERP - Main FastAPI entry point for Uvicorn / Railway.
Re-exports `app` from `server.py` to support `uvicorn main:app --host 0.0.0.0 --port $PORT`.
"""
import os
import uvicorn
from server import app

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run("main:app", host=host, port=port, reload=False)
