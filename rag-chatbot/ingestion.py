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
    """
    Extracts page text from a PDF.

    Word order *within* each text block/line coming out of pymupdf is
    correct (pymupdf handles Arabic shaping/word order fine on its own).
    The actual problem observed in this project's PDFs is *block-level*
    ordering: pymupdf's default extraction can emit separate text blocks
    (paragraphs) in content-stream order rather than visual top-to-bottom
    order, which swaps whole sentences/paragraphs relative to each other.

    This function extracts blocks explicitly via get_text("blocks") and
    re-sorts them by their vertical position (y0) then horizontal position
    (x0), so blocks come out top-to-bottom as a reader would expect,
    without touching the (already-correct) word order inside each block.

    NOTE: earlier versions of this function manually reordered *words*
    within lines (by x-coordinate, or via pymupdf's `sort=True` text mode).
    Both made results worse, because the real issue was never word order
    within a line/block -- it was the order blocks were emitted in.
    """
    doc = pymupdf.open(file_path)
    pages = []

    for i, page in enumerate(doc):
        # each block: (x0, y0, x1, y1, text, block_no, block_type)
        blocks = page.get_text("blocks")

        # keep only real text blocks (block_type == 0), drop images etc.
        text_blocks = [b for b in blocks if b[6] == 0 and b[4].strip()]

        # sort top-to-bottom, then left-to-right within the same line band
        text_blocks.sort(key=lambda b: (round(b[1], 1), b[0]))

        text = _fix_arabic("\n".join(b[4] for b in text_blocks))

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

    output = []

    for row in results:
        chunk_text = row[2]
        similarity = float(row[3])

        output.append({
            "source_file": row[0],
            "page_number": row[1],
            "chunk_text": chunk_text,
            "similarity": similarity,
        })

    output.sort(key=lambda x: x["similarity"], reverse=True)

    return output