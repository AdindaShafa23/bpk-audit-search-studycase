"""Pipeline asinkron (Celery).

  API --(enqueue)--> [fast]  extract_fast : teks asli PDF -> bila lengkap langsung indeks
                          \\--> [ocr]  ocr_and_index : OCR halaman scan -> indeks

Dua antrean terpisah agar OCR yang berat tidak membuat dokumen PDF-teks ikut antre."""
import logging
from datetime import datetime, timezone

from celery import Celery, Task

from . import classify, db, extract, storage
from .config import MAX_INDEX_CHARS, REDIS_URL
from .search import index_document

log = logging.getLogger("bpk.tasks")

celery_app = Celery("bpk", broker=REDIS_URL, backend=REDIS_URL)
celery_app.conf.update(
    task_acks_late=True,                 # pesan baru dihapus setelah selesai (aman bila worker mati)
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,        # tugas OCR berat: jangan menimbun
    task_default_queue="fast",
    task_routes={
        "app.tasks.extract_fast": {"queue": "fast"},
        "app.tasks.ocr_and_index": {"queue": "ocr"},
    },
    broker_transport_options={"visibility_timeout": 3 * 3600},
    result_expires=3600,
    task_track_started=True,
)


class PipelineTask(Task):
    """Tandai dokumen 'failed' bila retry habis."""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        doc_id = args[0] if args else None
        if doc_id:
            try:
                db.update_status(doc_id, "failed", error=str(exc)[:500])
            except Exception:  # pragma: no cover
                log.exception("gagal menandai failed")


def _finalize(doc_id: str, doc: dict, ex: extract.Extraction):
    """Klasifikasi -> update Postgres -> indeks ke Elasticsearch."""
    text = ex.text[:MAX_INDEX_CHARS]
    meta = classify.analyze(text)

    index_document(
        {
            "doc_id": doc_id,
            "institution": doc["institution"],
            "filename": doc["filename"],
            "doc_type": meta["doc_type"],
            "category": meta["category"],
            "contract_value": meta["contract_value"],
            "doc_date": doc["doc_date"].isoformat(),
            "indexed_at": datetime.now(timezone.utc).isoformat(),
            "ocr_used": ex.ocr_used,
            "page_count": ex.page_count,
            "content": text,
        }
    )
    db.update_status(
        doc_id,
        "done",
        ocr_used=ex.ocr_used,
        page_count=ex.page_count,
        doc_type=meta["doc_type"],
        category=meta["category"],
        contract_value=meta["contract_value"],
        error=None,
    )


@celery_app.task(
    base=PipelineTask, name="app.tasks.extract_fast", bind=True,
    autoretry_for=(Exception,), retry_backoff=5, retry_backoff_max=60, max_retries=3,
)
def extract_fast(self, doc_id: str):
    doc = db.get_document(doc_id)
    if not doc:
        return "missing"
    db.update_status(doc_id, "processing")

    data = storage.get_bytes(doc["object_key"])
    ex = extract.extract_native(data, doc["filename"])

    if ex.needs_ocr:
        # Serahkan ke antrean OCR; worker fast langsung bebas untuk dokumen berikutnya
        db.update_status(doc_id, "waiting_ocr", page_count=ex.page_count)
        ocr_and_index.apply_async(args=[doc_id], queue="ocr")
        return "queued_ocr"

    _finalize(doc_id, doc, ex)
    return "done"


@celery_app.task(
    base=PipelineTask, name="app.tasks.ocr_and_index", bind=True,
    autoretry_for=(Exception,), retry_backoff=10, retry_backoff_max=120, max_retries=2,
    acks_late=True, soft_time_limit=1800,
)
def ocr_and_index(self, doc_id: str):
    doc = db.get_document(doc_id)
    if not doc:
        return "missing"
    db.update_status(doc_id, "processing")

    data = storage.get_bytes(doc["object_key"])
    ex = extract.extract_with_ocr(data, doc["filename"])
    _finalize(doc_id, doc, ex)
    return "done"
