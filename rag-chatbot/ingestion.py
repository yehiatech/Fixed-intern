import os
import json
import uuid
import unicodedata
import boto3
import pymupdf  # PyMuPDF (import name "fitz" is the deprecated alias)
from bidi.algorithm import get_display  # pip install python-bidi
 
from db import get_connection
 
EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v2:0"  # multilingual, incl. Arabic
EMBEDDING_DIMENSIONS = 1024  # v2 also supports 512 / 256
 
CHUNK_SIZE_WORDS = 512   # approximate token count using whitespace-delimited words
CHUNK_OVERLAP_WORDS = 50
 
 
def _bedrock_client():
    return boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION", "us-east-1"))
 
 
def _fix_arabic(text: str) -> str:
    """
    Normalizes Arabic presentation-form glyphs to base characters, and
    reorders visual-order text (a common PDF-extraction artifact) back
    into logical order for storage/embedding.
    """
    text = unicodedata.normalize("NFKC", text)
    visual_markers = ("نم ", "يف ", "ىلع ")
    if any(m in text for m in visual_markers):
        text = "\n".join(get_display(ln) for ln in text.split("\n"))
    return text
 
 
def extract_pages(file_path: str) -> list[dict]:
    """Returns [{"page_number": 1, "text": "..."}, ...], 1-indexed pages."""
    doc = pymupdf.open(file_path)
    pages = []
    for i, page in enumerate(doc):
        text = _fix_arabic(page.get_text("text").strip())
        if text:
            pages.append({"page_number": i + 1, "text": text})
    doc.close()
    return pages
 
 
def chunk_text(text: str, chunk_size: int = CHUNK_SIZE_WORDS, overlap: int = CHUNK_OVERLAP_WORDS) -> list[str]:
    """Splits text into overlapping word-based chunks."""
    words = text.split()
    if not words:
        return []
 
    chunks = []
    start = 0
    step = max(chunk_size - overlap, 1)
    while start < len(words):
        chunk_words = words[start:start + chunk_size]
        chunks.append(" ".join(chunk_words))
        if start + chunk_size >= len(words):
            break
        start += step
    return chunks
 
 
def get_embedding(text: str) -> list[float]:
    """Calls Amazon Bedrock Titan Embeddings and returns a 1536-dim vector."""
    client = _bedrock_client()
    response = client.invoke_model(
        modelId=EMBEDDING_MODEL_ID,
        body=json.dumps({
            "inputText": text,
            "dimensions": EMBEDDING_DIMENSIONS,
            "normalize": True,
        }),
        contentType="application/json",
        accept="application/json",
    )
    payload = json.loads(response["body"].read())
    embedding = payload["embedding"]
    if len(embedding) != EMBEDDING_DIMENSIONS:
        raise ValueError(
            f"Unexpected embedding size {len(embedding)}, expected {EMBEDDING_DIMENSIONS}"
        )
    return embedding
 
 
def _vector_literal(embedding: list[float]) -> str:
    """
    Renders a Python float list as pgvector's expected text input format,
    e.g. "[0.123,0.456,...]". Passing this string with an explicit ::vector
    cast in SQL sidesteps ambiguous array-type inference (psycopg2's default
    list adapter can produce numeric[] literals that pgvector has no
    implicit/explicit cast for, causing "operator does not exist" errors).
    """
    return "[" + ",".join(repr(x) for x in embedding) + "]"
 
 
def ingest_pdf(file_path: str, organization_id: str) -> dict:
    """
    Full pipeline for one PDF: extract -> chunk -> embed -> store.
    Re-running this for the same (organization_id, file_path) overwrites
    previous chunks for that file (idempotent ingestion).
    """
    pages = extract_pages(file_path)
    source_file = os.path.basename(file_path)
 
    rows = []  # (id, org_id, source_file, page_number, chunk_index, chunk_text, embedding, metadata)
    for page in pages:
        page_chunks = chunk_text(page["text"])
        for idx, chunk in enumerate(page_chunks):
            embedding = get_embedding(chunk)
            metadata = {
                "org_id": organization_id,
                "page_number": page["page_number"],
                "source_file": source_file,
            }
            rows.append((
                str(uuid.uuid4()),
                organization_id,
                source_file,
                page["page_number"],
                idx,
                chunk,
                _vector_literal(embedding),
                json.dumps(metadata),
            ))
 
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                # Overwrite: remove any previously ingested chunks for this file/org
                cur.execute(
                    "DELETE FROM document_chunks WHERE organization_id = %s AND source_file = %s",
                    (organization_id, source_file),
                )
                cur.executemany(
                    """
                    INSERT INTO document_chunks
                        (id, organization_id, source_file, page_number, chunk_index, chunk_text, embedding, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s::vector, %s)
                    """,
                    rows,
                )
    finally:
        conn.close()
 
    return {
        "source_file": source_file,
        "pages_processed": len(pages),
        "chunks_ingested": len(rows),
    }
 
 
def search_chunks(query: str, organization_id: str, top_k: int = 5) -> list[dict]:
    """
    Cosine similarity search scoped to one organization.
    Uses pgvector's `<=>` cosine-distance operator (smaller = more similar);
    we return similarity = 1 - distance for readability.
    """
    query_embedding = _vector_literal(get_embedding(query))
 
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT source_file, page_number, chunk_text,
                       1 - (embedding <=> %s::vector) AS similarity
                FROM document_chunks
                WHERE organization_id = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (query_embedding, organization_id, query_embedding, top_k),
            )
            results = cur.fetchall()
    finally:
        conn.close()
 
    return [
        {
            "source_file": r[0],
            "page_number": r[1],
            "chunk_text": r[2],
            "similarity": float(r[3]),
        }
        for r in results
    ]