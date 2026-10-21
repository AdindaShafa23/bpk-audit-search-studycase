import logging
import os
import time
import uuid
from datetime import date, datetime
from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from . import db, search, storage
from .config import ALLOWED_EXT, MAX_UPLOAD_MB
from .tasks import celery_app

log = logging.getLogger("bpk.api")
app = FastAPI(title="BPK Audit Document Search", version="1.0.0")


@app.on_event("startup")
def startup():
    storage.ensure_bucket()
    search.ensure_index()
    # Postgres dibuat oleh db/init.sql; tunggu siap bila API start lebih dulu
    for i in range(30):
        try:
            db.institutions()
            break
        except Exception:
            time.sleep(2)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# ------------------------------------------------------------------- unggah
@app.post("/api/documents", status_code=202)
async def upload(
    files: List[UploadFile] = File(...),
    institution: str = Form(...),
    doc_date: Optional[str] = Form(None),
):
    """Unggah SANGAT CEPAT: simpan file ke MinIO, catat di Postgres, kirim ke antrean,
    lalu langsung balas 202. OCR/indeks berjalan di worker, bukan di request ini."""
    institution = institution.strip()
    if not institution:
        raise HTTPException(400, "Lembaga wajib diisi")
    try:
        d = date.fromisoformat(doc_date) if doc_date else date.today()
    except ValueError:
        raise HTTPException(400, "doc_date harus berformat YYYY-MM-DD")

    accepted = []
    for f in files:
        ext = os.path.splitext(f.filename or "")[1].lower()
        if ext not in ALLOWED_EXT:
            raise HTTPException(415, f"Tipe file {ext or '?'} tidak didukung")
        data = await f.read()
        if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
            raise HTTPException(413, f"Maksimal {MAX_UPLOAD_MB} MB per file")

        doc_id = str(uuid.uuid4())
        key = f"{doc_id}/{os.path.basename(f.filename)}"
        ctype = f.content_type or "application/octet-stream"

        storage.put_bytes(key, data, ctype)
        db.insert_document(doc_id, institution, f.filename, key, ctype, len(data), d)
        celery_app.send_task("app.tasks.extract_fast", args=[doc_id], queue="fast")
        accepted.append({"id": doc_id, "filename": f.filename, "status": "queued"})

    return {"accepted": accepted}


@app.get("/api/documents")
def documents(institution: Optional[str] = None, limit: int = Query(30, le=200)):
    rows = db.list_documents(institution, limit)
    for r in rows:
        r["id"] = str(r["id"])
        for k in ("uploaded_at", "processed_at"):
            if isinstance(r.get(k), datetime):
                r[k] = r[k].isoformat()
        if r.get("contract_value") is not None:
            r["contract_value"] = float(r["contract_value"])
    return rows


@app.get("/api/documents/{doc_id}/download")
def download(doc_id: str):
    doc = db.get_document(doc_id)
    if not doc:
        raise HTTPException(404, "Dokumen tidak ditemukan")
    return StreamingResponse(
        storage.stream(doc["object_key"]),
        media_type=doc["content_type"] or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{doc["filename"]}"'},
    )


@app.get("/api/institutions")
def institutions():
    return db.institutions()


# ------------------------------------------------------------------ pencarian
@app.get("/api/search")
def do_search(
    q: str = "",
    institution: Optional[str] = None,
    category: Optional[str] = None,
    doc_type: Optional[str] = None,
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=50),
):
    return search.search(q, institution, category, doc_type, page, size)


# ------------------------------------------------------------------ dashboard
@app.get("/api/dashboard")
def dashboard(institution: Optional[str] = None, interval: str = "week"):
    data = search.dashboard(institution, interval) or {}
    counts = db.status_counts(institution)
    incoming = db.incoming_by_institution()
    total_in = sum(counts.values())
    # gabungkan "dokumen masuk" (Postgres, termasuk yang masih antre) ke baris per-lembaga
    for row in data.get("by_institution", []):
        row["incoming"] = incoming.get(row["name"], row["indexed"])
    data.update(
        {
            "incoming_docs": total_in,
            "pipeline": {
                "queued": counts.get("queued", 0),
                "processing": counts.get("processing", 0),
                "waiting_ocr": counts.get("waiting_ocr", 0),
                "done": counts.get("done", 0),
                "failed": counts.get("failed", 0),
            },
            "institution": institution,
            "generated_at": datetime.utcnow().isoformat() + "Z",
        }
    )
    return data
