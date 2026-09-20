from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional

app = FastAPI(
    title="Arabic RAG Chatbot Microservice",
    version="0.1.0"
)

# Root Endpoint
@app.get("/")
def read_root():
    return {"service": "RAG Chatbot", "status": "running"}

# Health Check Endpoint (required by T-15 acceptance criteria)
@app.get("/health")
def health_check():
    return {"status": "ok"}

# Request Schemas (kept for T-16 / T-17, not used by placeholders yet)
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

# Placeholder Ingest Endpoint (real logic comes in T-16)
@app.post("/ingest")
def ingest_placeholder(request: IngestRequest):
    return {"message": "not implemented"}