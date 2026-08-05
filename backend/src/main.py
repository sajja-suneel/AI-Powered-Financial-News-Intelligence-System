# src/main.py
import sys
import asyncio

# Fix Windows ProactorEventLoop subprocess bug for Playwright/Crawl4AI
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.routes import router as api_router
from src.utils.logger import get_logger

logger = get_logger("api.main")

app = FastAPI(
    title="Tradl Financial News Intelligence API",
    description="Clean, self-contained REST API backend for context-aware financial intelligence."
)

# Enable CORS for external frontend applications
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register the separated endpoint routes
app.include_router(api_router)

if __name__ == "__main__":
    logger.info("Starting Tradl Financial API Server...")
    uvicorn.run("src.main:app", host="127.0.0.1", port=8000, reload=True)