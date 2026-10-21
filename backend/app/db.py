from contextlib import contextmanager

import psycopg2
import psycopg2.extras

from .config import POSTGRES_DSN


@contextmanager
def cursor():
    """Koneksi pendek per operasi (cukup untuk beban API ini)."""
    conn = psycopg2.connect(POSTGRES_DSN)
    try:
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                yield cur
    finally:
        conn.close()


def insert_document(doc_id, institution, filename, object_key, content_type, size_bytes, doc_date):
    with cursor() as cur:
        cur.execute(
            """
            INSERT INTO documents
                (id, institution, filename, object_key, content_type, size_bytes, doc_date, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'queued')
            """,
            (doc_id, institution, filename, object_key, content_type, size_bytes, doc_date),
        )


def get_document(doc_id):
    with cursor() as cur:
        cur.execute("SELECT * FROM documents WHERE id = %s", (doc_id,))
        return cur.fetchone()


def update_status(doc_id, status, **fields):
    sets = ["status = %s"]
    vals = [status]
    for k, v in fields.items():
        sets.append(f"{k} = %s")
        vals.append(v)
    if status in ("done", "failed"):
        sets.append("processed_at = now()")
    vals.append(doc_id)
    with cursor() as cur:
        cur.execute(f"UPDATE documents SET {', '.join(sets)} WHERE id = %s", vals)


def list_documents(institution=None, limit=30):
    where, args = "", []
    if institution:
        where = "WHERE institution = %s"
        args.append(institution)
    args.append(limit)
    with cursor() as cur:
        cur.execute(
            f"""
            SELECT id, institution, filename, status, ocr_used, doc_type, category,
                   contract_value, page_count, error, uploaded_at, processed_at
            FROM documents {where}
            ORDER BY uploaded_at DESC LIMIT %s
            """,
            args,
        )
        return cur.fetchall()


def status_counts(institution=None):
    where, args = "", []
    if institution:
        where = "WHERE institution = %s"
        args.append(institution)
    with cursor() as cur:
        cur.execute(
            f"SELECT status, count(*) AS n FROM documents {where} GROUP BY status", args
        )
        return {r["status"]: r["n"] for r in cur.fetchall()}


def incoming_by_institution():
    """Jumlah dokumen masuk (semua status) per lembaga."""
    with cursor() as cur:
        cur.execute(
            "SELECT institution, count(*) AS n FROM documents GROUP BY institution"
        )
        return {r["institution"]: r["n"] for r in cur.fetchall()}


def institutions():
    with cursor() as cur:
        cur.execute("SELECT DISTINCT institution FROM documents ORDER BY institution")
        return [r["institution"] for r in cur.fetchall()]
