"""
Database connection helper.
Reads connection settings from environment variables (see .env.example):
DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
"""
import os
import psycopg2
from pgvector.psycopg2 import register_vector
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    """
    Opens a new psycopg2 connection and registers the pgvector type
    so Python lists can be inserted/read directly as `vector` columns.
    """
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "db"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "ai_callcenter"),
        user=os.getenv("DB_USER", "admin"),
        password=os.getenv("DB_PASSWORD", "supersecretpassword"),
    )
    register_vector(conn)
    return conn