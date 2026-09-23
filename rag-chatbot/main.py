from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Literal
import os
import shutil

from ingestion import ingest_pdf
from chat import handle_chat, submit_feedback

app = FastAPI(
    title="Arabic RAG Chatbot Microservice",
    version="0.1.0"
)

# Add CORS Middleware to allow requests from the chat widget
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
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
    history: list[dict] = []

class IngestRequest(BaseModel):
    organization_id: str
    file_path: str

class FeedbackRequest(BaseModel):
    interaction_id: str
    rating: Literal["up", "down"]

# Chat Endpoint
@app.post("/chat")
def chat(request: ChatRequest):
    try:
        result = handle_chat(request.query, request.organization_id, request.user_id, request.history)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return result

# Original Ingest Endpoint
@app.post("/ingest")
def ingest(request: IngestRequest):
    try:
        result = ingest_pdf(request.file_path, request.organization_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"File not found: {request.file_path}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"message": "ingested", **result}

# NEW: File Upload Endpoint
@app.post("/upload")
async def upload_pdf(organization_id: str = Form(...), file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    
    # Save the file temporarily
    temp_file_path = f"/tmp/{file.filename}"
    os.makedirs("/tmp", exist_ok=True)
    with open(temp_file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Run ingestion
    try:
        result = ingest_pdf(temp_file_path, organization_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
            
    return {"message": "file uploaded and ingested", "filename": file.filename, **result}

# Feedback Endpoint
@app.post("/feedback")
def feedback(request: FeedbackRequest):
    try:
        result = submit_feedback(request.interaction_id, request.rating)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"message": "feedback recorded", **result}