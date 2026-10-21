"""Elasticsearch: mapping (analyzer Indonesia), indexing, pencarian fuzzy, agregasi dashboard."""
import time
from typing import Optional

from elasticsearch import Elasticsearch, NotFoundError

from .config import ES_INDEX, ES_URL

_es = None
_index_ready = False

INDEX_BODY = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "analysis": {
            "filter": {
                "id_stop": {"type": "stop", "stopwords": "_indonesian_"},
                "id_stemmer": {"type": "stemmer", "language": "indonesian"},
            },
            "analyzer": {
                # Stemming Indonesia: "pengadaan" / "mengadakan" / "diadakan" -> akar sama
                "id_text": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["lowercase", "asciifolding", "id_stop", "id_stemmer"],
                },
                # Tanpa stemming: jaring pengaman untuk salah ketik (fuzzy)
                "id_plain": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["lowercase", "asciifolding"],
                },
            },
        },
    },
    "mappings": {
        "properties": {
            "doc_id": {"type": "keyword"},
            "institution": {"type": "keyword"},
            "filename": {
                "type": "text",
                "analyzer": "id_plain",
                "fields": {"raw": {"type": "keyword"}},
            },
            "doc_type": {"type": "keyword"},
            "category": {"type": "keyword"},
            "contract_value": {"type": "double"},
            "doc_date": {"type": "date"},
            "indexed_at": {"type": "date"},
            "ocr_used": {"type": "boolean"},
            "page_count": {"type": "integer"},
            "content": {
                "type": "text",
                "analyzer": "id_text",
                "fields": {"plain": {"type": "text", "analyzer": "id_plain"}},
            },
        }
    },
}


def es() -> Elasticsearch:
    global _es
    if _es is None:
        _es = Elasticsearch(ES_URL, request_timeout=30)
    return _es


def ensure_index(retries: int = 40):
    global _index_ready
    if _index_ready:
        return
    for i in range(retries):
        try:
            if not es().indices.exists(index=ES_INDEX):
                es().indices.create(index=ES_INDEX, body=INDEX_BODY)
            _index_ready = True
            return
        except Exception as e:  # ES belum siap / race antar proses
            if "resource_already_exists" in str(e):
                _index_ready = True
                return
            if i == retries - 1:
                raise
            time.sleep(3)


def index_document(doc: dict):
    ensure_index()
    es().index(index=ES_INDEX, id=doc["doc_id"], document=doc, refresh="wait_for")


# ----------------------------------------------------------------- pencarian
def _filters(institution=None, category=None, doc_type=None):
    f = []
    if institution:
        f.append({"term": {"institution": institution}})
    if category:
        f.append({"term": {"category": category}})
    if doc_type:
        f.append({"term": {"doc_type": doc_type}})
    return f


def search(q: str, institution=None, category=None, doc_type=None, page=1, size=10):
    ensure_index()
    filters = _filters(institution, category, doc_type)

    if q.strip():
        text_query = {
            "bool": {
                "should": [
                    # 1) analyzer ber-stemming: kata berimbuhan -> akar kata sama
                    {
                        "match": {
                            "content": {
                                "query": q,
                                "operator": "and",
                                "fuzziness": "AUTO",
                                "prefix_length": 1,
                                "boost": 2,
                            }
                        }
                    },
                    # 2) tanpa stemming + fuzzy: toleransi salah ketik
                    {
                        "match": {
                            "content.plain": {
                                "query": q,
                                "operator": "and",
                                "fuzziness": "AUTO",
                                "prefix_length": 1,
                            }
                        }
                    },
                    # 3) frasa persis -> naik peringkat
                    {"match_phrase": {"content": {"query": q, "boost": 4, "slop": 2}}},
                    # 4) nama file
                    {"match": {"filename": {"query": q, "fuzziness": "AUTO", "boost": 1.5}}},
                ],
                "minimum_should_match": 1,
            }
        }
    else:
        text_query = {"match_all": {}}

    body = {
        "query": {"bool": {"must": [text_query], "filter": filters}},
        "from": (page - 1) * size,
        "size": size,
        "_source": [
            "doc_id", "institution", "filename", "doc_type", "category",
            "contract_value", "doc_date", "ocr_used", "page_count",
        ],
        "highlight": {
            "require_field_match": False,
            "encoder": "html",
            "pre_tags": ["<mark>"],
            "post_tags": ["</mark>"],
            "fields": {
                "content": {"fragment_size": 180, "number_of_fragments": 2},
                "content.plain": {"fragment_size": 180, "number_of_fragments": 2},
            },
        },
        "track_total_hits": True,
    }
    res = es().search(index=ES_INDEX, body=body)
    hits = []
    for h in res["hits"]["hits"]:
        hl = h.get("highlight", {})
        snippets = hl.get("content") or hl.get("content.plain") or []
        src = h["_source"]
        src["score"] = h["_score"]
        src["snippets"] = snippets
        hits.append(src)
    return {"total": res["hits"]["total"]["value"], "page": page, "size": size, "hits": hits}


# ----------------------------------------------------------------- dashboard
def dashboard(institution: Optional[str] = None, interval: str = "week"):
    ensure_index()
    if interval not in ("day", "week", "month"):
        interval = "week"
    q = {"bool": {"filter": _filters(institution)}}
    body = {
        "size": 0,
        "query": q,
        "track_total_hits": True,
        "aggs": {
            "contracts": {
                "filter": {"term": {"doc_type": "Kontrak"}},
                "aggs": {"total_value": {"sum": {"field": "contract_value"}}},
            },
            "ocr": {"filter": {"term": {"ocr_used": True}}},
            "by_category": {"terms": {"field": "category", "size": 20}},
            "by_type": {"terms": {"field": "doc_type", "size": 10}},
            "by_institution": {
                "terms": {"field": "institution", "size": 100},
                "aggs": {
                    "contracts": {
                        "filter": {"term": {"doc_type": "Kontrak"}},
                        "aggs": {"total_value": {"sum": {"field": "contract_value"}}},
                    }
                },
            },
            "trend": {
                "date_histogram": {
                    "field": "doc_date",
                    "calendar_interval": interval,
                    "format": "yyyy-MM-dd",
                    "min_doc_count": 0,
                },
                "aggs": {"cat": {"terms": {"field": "category", "size": 20}}},
            },
        },
    }
    try:
        res = es().search(index=ES_INDEX, body=body)
    except NotFoundError:
        return None
    a = res["aggregations"]

    labels, series = [], {}
    cats = [b["key"] for b in a["by_category"]["buckets"]]
    for c in cats:
        series[c] = []
    for b in a["trend"]["buckets"]:
        labels.append(b["key_as_string"])
        got = {x["key"]: x["doc_count"] for x in b["cat"]["buckets"]}
        for c in cats:
            series[c].append(got.get(c, 0))

    return {
        "indexed_docs": res["hits"]["total"]["value"],
        "total_contract_value": a["contracts"]["total_value"]["value"] or 0,
        "contract_count": a["contracts"]["doc_count"],
        "ocr_docs": a["ocr"]["doc_count"],
        "by_category": [{"name": b["key"], "count": b["doc_count"]} for b in a["by_category"]["buckets"]],
        "by_type": [{"name": b["key"], "count": b["doc_count"]} for b in a["by_type"]["buckets"]],
        "by_institution": [
            {
                "name": b["key"],
                "indexed": b["doc_count"],
                "contract_value": b["contracts"]["total_value"]["value"] or 0,
            }
            for b in a["by_institution"]["buckets"]
        ],
        "trend": {"interval": interval, "labels": labels, "series": series},
    }
