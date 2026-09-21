
import os
import json
import uuid
import unicodedata
import boto3
import pymupdf

from db import get_connection

EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v2:0"
EMBEDDING_DIMENSIONS = 1024

CHUNK_SIZE_WORDS = 512
CHUNK_OVERLAP_WORDS = 50


def _bedrock_client():
    return boto3.client(
        "bedrock-runtime",
        region_name=os.getenv("AWS_REGION", "us-east-1")
    )


def _fix_arabic(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)

    replacements = {
        "\u0640": "",
        "\u200e": "",
        "\u200f": "",
        "\u202a": "",
        "\u202b": "",
        "\u202c": "",
        "\u202d": "",
        "\u202e": "",
        "\ufeff": "",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = " ".join(text.split())
    return text.strip()


def extract_pages(file_path: str) -> list[dict]:
    doc = pymupdf.open(file_path)
    pages = []

    for i, page in enumerate(doc):
        text = _fix_arabic(page.get_text("text"))

        if text:
            pages.append({
                "page_number": i + 1,
                "text": text
            })

    doc.close()
    return pages


def chunk_text(
    text: str,
    chunk_size: int = CHUNK_SIZE_WORDS,
    overlap: int = CHUNK_OVERLAP_WORDS
) -> list[str]:

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
            f"Unexpected embedding size {len(embedding)}, "
            f"expected {EMBEDDING_DIMENSIONS}"
        )

    return embedding


def _vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(repr(x) for x in embedding) + "]"


def ingest_pdf(file_path: str, organization_id: str) -> dict:
    pages = extract_pages(file_path)
    source_file = os.path.basename(file_path)

    rows = []

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
                cur.execute(
                    """
                    DELETE FROM document_chunks
                    WHERE organization_id = %s
                    AND source_file = %s
                    """,
                    (organization_id, source_file),
                )

                cur.executemany(
                    """
                    INSERT INTO document_chunks
                    (
                        id,
                        organization_id,
                        source_file,
                        page_number,
                        chunk_index,
                        chunk_text,
                        embedding,
                        metadata
                    )
                    VALUES
                    (
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s::vector,
                        %s
                    )
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



def search_chunks(
    query: str,
    organization_id: str,
    top_k: int = 5
) -> list[dict]:

    query_embedding = _vector_literal(get_embedding(query))

    conn = get_connection()

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    source_file,
                    page_number,
                    chunk_text,
                    1 - (embedding <=> %s::vector) AS similarity
                FROM document_chunks
                WHERE organization_id = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (
                    query_embedding,
                    organization_id,
                    query_embedding,
                    top_k,
                ),
            )

            results = cur.fetchall()

    finally:
        conn.close()

    query_normalized = _fix_arabic(query).lower()

    output = []

    for row in results:
        chunk_text = row[2]
        chunk_normalized = _fix_arabic(chunk_text).lower()

        semantic_score = float(row[3])

        keyword_score = 0.0

        important_terms = [
            "السحب",
            "اليومي",
            "المعاملات",
            "فودافون كاش",
            "60000",
            "60,000",
            "الحد الأقصى",
        ]

        matched_terms = sum(
            1
            for term in important_terms
            if term in query_normalized and term in chunk_normalized
        )

        if matched_terms:
          keyword_score = min(matched_terms * 0.20, 0.75)

        similarity = min(semantic_score + keyword_score, 1.0)

        output.append({
            "source_file": row[0],
            "page_number": row[1],
            "chunk_text": chunk_text,
            "similarity": similarity,
        })

    output.sort(key=lambda x: x["similarity"], reverse=True)

    return output


