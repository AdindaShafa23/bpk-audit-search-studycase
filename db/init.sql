CREATE TABLE IF NOT EXISTS documents (
    id              UUID PRIMARY KEY,
    institution     TEXT        NOT NULL,
    filename        TEXT        NOT NULL,
    object_key      TEXT        NOT NULL,
    content_type    TEXT,
    size_bytes      BIGINT,
    doc_date        DATE        NOT NULL DEFAULT CURRENT_DATE,
    status          TEXT        NOT NULL DEFAULT 'queued',   -- queued|processing|waiting_ocr|done|failed
    ocr_used        BOOLEAN     NOT NULL DEFAULT FALSE,
    page_count      INTEGER,
    doc_type        TEXT,
    category        TEXT,
    contract_value  NUMERIC(20,0),
    error           TEXT,
    uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_documents_institution ON documents (institution);
CREATE INDEX IF NOT EXISTS idx_documents_status      ON documents (status);
CREATE INDEX IF NOT EXISTS idx_documents_uploaded    ON documents (uploaded_at DESC);
