# config/database.py
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from qdrant_client import QdrantClient
from pymongo import MongoClient

# Load variables from .env file
load_dotenv()

class DbConnectionManager:
    """
    Manages client connections to Neon PostgreSQL and Qdrant Cloud.
    """
    DATABASE_URL = os.getenv("DATABASE_URL")
    QDRANT_HOST = os.getenv("QDRANT_HOST")
    QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

    if not DATABASE_URL:
        raise ValueError("DATABASE_URL is not set in the .env file")
    if not QDRANT_HOST or not QDRANT_API_KEY:
        raise ValueError("QDRANT_HOST or QDRANT_API_KEY is not set in the .env file")

    # 1. Establish PostgreSQL Engine and Session Configurations
    engine = create_engine(
        DATABASE_URL, 
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args={"connect_timeout": 15}
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base = declarative_base()

    # 2. Establish Qdrant Cloud Client Configuration
    qdrant_client = QdrantClient(
        url=QDRANT_HOST,
        api_key=QDRANT_API_KEY,
        timeout=60.0
    )

    # 3. Establish MongoDB Client Configuration for Chat History
    MONGO_URI = os.getenv("MONGO_URI")
    MONGO_DATABASE = os.getenv("MONGO_DATABASE", "financial_chatbot")
    mongo_client = None
    mongo_db = None
    if MONGO_URI:
        try:
            mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
            mongo_db = mongo_client[MONGO_DATABASE]
            # Verify connection works
            mongo_client.admin.command('ping')
            print(f"[MONGODB SUCCESS] Connected to MongoDB Atlas. Database: '{MONGO_DATABASE}'")
        except Exception as e:
            print(f"[MONGODB CONNECTION ERROR] Failed to connect to MongoDB at '{MONGO_URI}': {e}")
            mongo_db = None
    else:
        print("[MONGODB WARNING] MONGO_URI environment variable is not set. Chat history storage will be disabled.")

    @staticmethod
    def get_db():
        """Dependency helper to get PostgreSQL session"""
        db = DbConnectionManager.SessionLocal()
        try:
            yield db
        finally:
            db.close()

# ----------------------------------------------------
# Module-level aliases to keep other files backward-compatible
# ----------------------------------------------------
engine = DbConnectionManager.engine
SessionLocal = DbConnectionManager.SessionLocal
Base = DbConnectionManager.Base
qdrant_client = DbConnectionManager.qdrant_client
mongo_db = DbConnectionManager.mongo_db
get_db = DbConnectionManager.get_db