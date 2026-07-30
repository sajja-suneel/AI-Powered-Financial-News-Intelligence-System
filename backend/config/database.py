import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from qdrant_client import QdrantClient

# Load variables from .env file
load_dotenv()

# 1. PostgreSQL (Neon) Connection Setup
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in the .env file")

# Use pool_pre_ping to automatically reconnect if Neon serverless goes cold
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 2. Qdrant Cloud Connection Setup
QDRANT_HOST = os.getenv("QDRANT_HOST")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

if not QDRANT_HOST or not QDRANT_API_KEY:
    raise ValueError("QDRANT_HOST or QDRANT_API_KEY is not set in the .env file")

qdrant_client = QdrantClient(
    url=QDRANT_HOST,
    api_key=QDRANT_API_KEY
)

def get_db():
    """Dependency helper to get PostgreSQL session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()