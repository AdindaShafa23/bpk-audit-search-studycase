import os

POSTGRES_DSN = os.getenv(
    "POSTGRES_DSN", "postgresql://bpk:bpk@postgres:5432/bpk"
)
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
ES_URL = os.getenv("ES_URL", "http://elasticsearch:9200")
ES_INDEX = os.getenv("ES_INDEX", "bpk-documents")

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "bpk-raw-documents")

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "50"))
ALLOWED_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}

# Halaman PDF dianggap "tidak punya teks" (perlu OCR) bila teks asli < N karakter
MIN_CHARS_PER_PAGE = int(os.getenv("MIN_CHARS_PER_PAGE", "40"))
OCR_DPI = int(os.getenv("OCR_DPI", "200"))
OCR_LANG = os.getenv("OCR_LANG", "ind+eng")
MAX_INDEX_CHARS = int(os.getenv("MAX_INDEX_CHARS", "1500000"))
