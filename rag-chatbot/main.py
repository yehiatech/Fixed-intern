from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

from ingestion import ingest_pdf

app = FastAPI(
    title="Arabic RAG Chatbot Microservice",
    version="0.1.0"
)

# Root Endpoint
@app.get("/")
def read_root():
    return {"service": "RAG Chatbot", "status": "running"}

# Health Check Endpoint
@app.get("/health")
def health_check():
    return {"status": "ok"}

# Request Schemas
class ChatRequest(BaseModel):
    organization_id: str
    user_id: Optional[str] = None
    query: str

class IngestRequest(BaseModel):
    organization_id: str
    file_path: str

# Placeholder Chat Endpoint (real logic comes in T-17)
@app.post("/chat")
def chat_placeholder(request: ChatRequest):
    return {"message": "not implemented"}

# Ingest Endpoint (T-16: real PDF -> chunk -> embed -> pgvector pipeline)
@app.post("/ingest")
def ingest(request: IngestRequest):
    try:
        result = ingest_pdf(request.file_path, request.organization_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"File not found: {request.file_path}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"message": "ingested", **result}