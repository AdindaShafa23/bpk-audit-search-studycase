"""Ekstraksi metadata sederhana (jenis dokumen, kategori belanja, nilai kontrak)
berbasis aturan. Cukup untuk demo; di produksi bisa diganti model ML/LLM."""
import re

CATEGORY_KEYWORDS = {
    "Bahan Bakar": [
        "bahan bakar", "bbm", "solar", "pertalite", "pertamax", "dexlite",
        "spbu", "bensin", "voucher bbm",
    ],
    "Jasa Konsultan": [
        "konsultan", "konsultansi", "konsultasi", "tenaga ahli", "studi kelayakan",
        "jasa konsultan", "pendampingan", "kajian",
    ],
    "Belanja Modal": [
        "belanja modal", "pengadaan gedung", "peralatan dan mesin", "aset tetap",
        "konstruksi", "pembangunan", "renovasi gedung", "pengadaan kendaraan",
    ],
    "Belanja Perjalanan Dinas": [
        "perjalanan dinas", "sppd", "tiket pesawat", "penginapan", "uang harian",
    ],
    "Belanja Barang": [
        "alat tulis", "atk", "belanja barang", "persediaan", "bahan habis pakai",
        "cetak", "fotokopi",
    ],
    "Belanja Pegawai": [
        "gaji", "tunjangan", "honorarium", "lembur", "belanja pegawai",
    ],
}

DOC_TYPE_KEYWORDS = {
    "Kontrak": ["surat perjanjian", "kontrak", "spk", "surat perintah kerja", "para pihak"],
    "Nota": ["nota", "kuitansi", "kwitansi", "faktur", "invoice", "struk"],
    "Laporan Realisasi": ["laporan realisasi", "realisasi anggaran", "realisasi belanja"],
}

# Rp 1.250.000.000,00 | Rp. 350.000 | Rp25000000
RUPIAH_RE = re.compile(
    r"Rp\.?\s*([0-9]{1,3}(?:[.,][0-9]{3})+|[0-9]+)(?:[,.][0-9]{1,2})?", re.IGNORECASE
)
CONTRACT_HINT_RE = re.compile(
    r"(nilai\s+kontrak|nilai\s+pekerjaan|harga\s+kontrak|harga\s+pekerjaan|"
    r"nilai\s+perjanjian|sebesar|senilai)",
    re.IGNORECASE,
)


def _count_hits(text: str, words) -> int:
    return sum(text.count(w) for w in words)


def detect_doc_type(text: str) -> str:
    t = text.lower()
    scores = {k: _count_hits(t, v) for k, v in DOC_TYPE_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "Lainnya"


def detect_category(text: str) -> str:
    t = text.lower()
    scores = {k: _count_hits(t, v) for k, v in CATEGORY_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "Lainnya"


def parse_rupiah(raw: str) -> int:
    digits = re.sub(r"[^0-9]", "", raw)
    return int(digits) if digits else 0


def extract_contract_value(text: str):
    """Ambil nilai kontrak: prioritas angka pada baris yang memuat petunjuk
    'nilai kontrak/sebesar/...', jika tidak ada pakai angka Rp terbesar."""
    hinted, allvals = [], []
    for line in text.splitlines():
        for m in RUPIAH_RE.finditer(line):
            v = parse_rupiah(m.group(1))
            if v <= 0:
                continue
            allvals.append(v)
            if CONTRACT_HINT_RE.search(line):
                hinted.append(v)
    if hinted:
        return max(hinted)
    if allvals:
        return max(allvals)
    return None


def analyze(text: str) -> dict:
    doc_type = detect_doc_type(text)
    return {
        "doc_type": doc_type,
        "category": detect_category(text),
        # nilai kontrak hanya dihitung untuk dokumen berjenis Kontrak
        "contract_value": extract_contract_value(text) if doc_type == "Kontrak" else None,
    }
