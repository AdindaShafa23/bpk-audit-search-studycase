import io
import time

from minio import Minio

from .config import MINIO_ACCESS_KEY, MINIO_BUCKET, MINIO_ENDPOINT, MINIO_SECRET_KEY

_client = None


def client() -> Minio:
    global _client
    if _client is None:
        _client = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=False,
        )
    return _client


def ensure_bucket(retries: int = 30):
    for i in range(retries):
        try:
            c = client()
            if not c.bucket_exists(MINIO_BUCKET):
                c.make_bucket(MINIO_BUCKET)
            return
        except Exception:
            if i == retries - 1:
                raise
            time.sleep(2)


def put_bytes(key: str, data: bytes, content_type: str):
    client().put_object(
        MINIO_BUCKET, key, io.BytesIO(data), length=len(data), content_type=content_type
    )


def get_bytes(key: str) -> bytes:
    resp = client().get_object(MINIO_BUCKET, key)
    try:
        return resp.read()
    finally:
        resp.close()
        resp.release_conn()


def stream(key: str):
    """Mengembalikan (generator chunk, closer)."""
    resp = client().get_object(MINIO_BUCKET, key)

    def gen():
        try:
            for chunk in resp.stream(64 * 1024):
                yield chunk
        finally:
            resp.close()
            resp.release_conn()

    return gen()
