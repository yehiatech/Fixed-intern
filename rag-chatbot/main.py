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
# --- Admin & Setup Endpoints ---
class OrgCreateRequest(BaseModel):
    name: str

class UserCreateRequest(BaseModel):
    username: str
    password: str
    role: str
    organization_id: Optional[str] = None

@app.post("/organizations")
def create_organization(req: OrgCreateRequest):
    from db import get_connection
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO organizations (name) VALUES (%s) RETURNING id", (req.name,))
                org_id = cur.fetchone()[0]
        return {"id": org_id, "name": req.name}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

@app.post("/users")
def create_user(req: UserCreateRequest):
    from db import get_connection
    import hashlib
    conn = get_connection()
    pw_hash = hashlib.sha256(req.password.encode()).hexdigest()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO users (username, password_hash, role, organization_id) VALUES (%s, %s, %s, %s) RETURNING id", 
                    (req.username, pw_hash, req.role, req.organization_id)
                )
                user_id = cur.fetchone()[0]
        return {"id": user_id, "username": req.username, "role": req.role}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

@app.get("/organizations")
def list_organizations():
    from db import get_connection
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, name FROM organizations")
                orgs = [{"id": row[0], "name": row[1]} for row in cur.fetchall()]
        return {"organizations": orgs}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


# --- API Endpoints ---
class LoginRequest(BaseModel):
    username: str

@app.post("/api/login")
def login(req: LoginRequest):
    from db import get_connection
    from fastapi import HTTPException
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT role, organization_id FROM users WHERE username = %s", (req.username,))
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=401, detail="Invalid username")
                return {"role": row[0], "organization_id": row[1]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

@app.get("/api/organizations")
def get_all_organizations():
    from db import get_connection
    from fastapi import HTTPException
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM organizations")
                columns = [desc[0] for desc in cur.description]
                orgs = [dict(zip(columns, row)) for row in cur.fetchall()]
        return {"organizations": orgs}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

@app.delete("/api/organizations/{id}")
def delete_organization(id: str):
    from db import get_connection
    from fastapi import HTTPException
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM organizations WHERE id = %s", (id,))
        return {"message": "Organization deleted"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

class StatusUpdateRequest(BaseModel):
    status: str

@app.put("/api/organizations/{id}/status")
def update_organization_status(id: str, req: StatusUpdateRequest):
    from db import get_connection
    from fastapi import HTTPException
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE organizations SET status = %s WHERE id = %s", (req.status, id))
        return {"message": "Status updated"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

@app.get("/api/organizations/{id}/users")
def get_org_users(id: str):
    from db import get_connection
    from fastapi import HTTPException
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, username, role FROM users WHERE organization_id = %s", (id,))
                users = [{"id": row[0], "username": row[1], "role": row[2]} for row in cur.fetchall()]
        return {"users": users}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

@app.delete("/api/users/{id}")
def delete_user(id: str):
    from db import get_connection
    from fastapi import HTTPException
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM users WHERE id = %s", (id,))
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()
