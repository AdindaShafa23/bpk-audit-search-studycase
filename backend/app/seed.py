"""Seeder: membuat dokumen contoh (PDF bertext + PDF hasil scan/gambar) dan mengunggahnya
lewat API sehingga seluruh pipeline (antrean -> OCR -> indeks -> dashboard) ikut berjalan.

Pakai:  docker compose exec api python -m app.seed --count 30
Semua data FIKTIF, hanya untuk demo."""
import argparse
import io
import os
import random
import textwrap
from datetime import date, timedelta

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

API = os.getenv("SEED_API", "http://localhost:8000")

INSTITUTIONS = [
    "Kementerian Perhubungan",
    "Dinas Pekerjaan Umum Provinsi Jawa Timur",
    "Pemerintah Kota Surabaya",
    "Kementerian Kesehatan",
]

# (kategori, judul pekerjaan, rentang nilai, uraian)
CONTRACT_TEMPLATES = [
    ("Bahan Bakar", "Pengadaan Bahan Bakar Minyak (BBM) Kendaraan Operasional",
     (80_000_000, 450_000_000),
     "Penyediaan solar dan pertamax untuk kendaraan dinas melalui voucher BBM pada SPBU yang ditunjuk."),
    ("Jasa Konsultan", "Jasa Konsultansi Penyusunan Studi Kelayakan",
     (150_000_000, 900_000_000),
     "Pekerjaan jasa konsultan perencanaan meliputi studi kelayakan, kajian teknis, dan pendampingan oleh tenaga ahli."),
    ("Belanja Modal", "Belanja Modal Pembangunan Gedung Layanan",
     (1_500_000_000, 12_000_000_000),
     "Belanja modal untuk pembangunan konstruksi gedung dan pengadaan peralatan dan mesin sebagai aset tetap."),
    ("Belanja Barang", "Pengadaan Alat Tulis Kantor dan Bahan Habis Pakai",
     (25_000_000, 180_000_000),
     "Belanja barang persediaan berupa alat tulis kantor (ATK), cetak, dan fotokopi untuk kebutuhan satuan kerja."),
    ("Belanja Perjalanan Dinas", "Belanja Perjalanan Dinas Dalam Negeri",
     (40_000_000, 260_000_000),
     "Perjalanan dinas pegawai meliputi tiket pesawat, penginapan, dan uang harian sesuai SPPD."),
]


def rupiah(n: int) -> str:
    return "Rp " + f"{n:,}".replace(",", ".") + ",00"


def kontrak_text(inst, tpl, n, d):
    cat, judul, (lo, hi), uraian = tpl
    nilai = random.randrange(lo, hi, 1_000_000)
    return f"""SURAT PERJANJIAN KERJA (KONTRAK)
Nomor: {n:03d}/SPK/{d.year}/{random.randint(100, 999)}

Pada hari ini tanggal {d.strftime('%d-%m-%Y')}, para pihak yang bertanda tangan di bawah ini:
Pihak Pertama : Pejabat Pembuat Komitmen {inst}
Pihak Kedua   : PT {random.choice(['Karya Mandiri', 'Sinar Nusantara', 'Cipta Bangun', 'Mitra Andalan'])}

Pasal 1 Lingkup Pekerjaan
{judul}. {uraian}

Pasal 2 Nilai Kontrak
Nilai kontrak pekerjaan ini sebesar {rupiah(nilai)} sudah termasuk pajak.

Pasal 3 Jangka Waktu
Pekerjaan dilaksanakan selama {random.choice([60, 90, 120, 180])} hari kalender sejak SPK diterbitkan.
""", cat


def nota_text(inst, tpl, n, d):
    cat, judul, _, _ = tpl
    total = random.randrange(250_000, 15_000_000, 5_000)
    return f"""NOTA PEMBELIAN / KUITANSI
No. {d.year}{n:05d}
Tanggal : {d.strftime('%d-%m-%Y')}
Dibayar oleh : {inst}
Untuk pembayaran : {judul}

Jumlah yang dibayarkan {rupiah(total)}
Terima kasih.
""", cat


def laporan_text(inst, tpl, n, d):
    cat, judul, (lo, hi), _ = tpl
    pagu = random.randrange(lo, hi, 1_000_000)
    real = int(pagu * random.uniform(0.55, 0.98))
    return f"""LAPORAN REALISASI ANGGARAN
{inst}
Periode: {d.strftime('%B %Y')}

Uraian kegiatan : {judul}
Pagu anggaran   : {rupiah(pagu)}
Realisasi belanja: {rupiah(real)}
Persentase realisasi: {real * 100 // pagu}%
""", cat


def make_text_pdf(text: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 800
    for line in text.splitlines():
        for part in textwrap.wrap(line, 90) or [""]:
            c.drawString(50, y, part)
            y -= 16
    c.save()
    return buf.getvalue()


def make_scan_pdf(text: str) -> bytes:
    """PDF yang hanya berisi gambar (tanpa teks) + sedikit noise & rotasi = 'hasil scan'."""
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    try:
        font = ImageFont.truetype(font_path, 30)
    except OSError:
        font = ImageFont.load_default()
    img = Image.new("L", (1654, 2339), 245)  # A4 @ 200 dpi
    d = ImageDraw.Draw(img)
    y = 140
    for line in text.splitlines():
        for part in textwrap.wrap(line, 60) or [""]:
            d.text((120, y), part, fill=25, font=font)
            y += 46
    img = img.rotate(random.uniform(-0.8, 0.8), fillcolor=245)
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "PDF", resolution=200.0)
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=30)
    ap.add_argument("--scan-ratio", type=float, default=0.35, help="porsi dokumen hasil scan (perlu OCR)")
    ap.add_argument("--api", default=API)
    a = ap.parse_args()

    random.seed(42)
    today = date.today()
    ok = 0
    for i in range(1, a.count + 1):
        inst = random.choice(INSTITUTIONS)
        tpl = random.choice(CONTRACT_TEMPLATES)
        d = today - timedelta(days=random.randint(0, 56))  # ~2 bulan audit
        kind = random.choices(["kontrak", "nota", "laporan"], weights=[5, 3, 2])[0]
        text, _cat = {"kontrak": kontrak_text, "nota": nota_text, "laporan": laporan_text}[kind](inst, tpl, i, d)

        scanned = random.random() < a.scan_ratio
        pdf = make_scan_pdf(text) if scanned else make_text_pdf(text)
        name = f"{kind}_{i:03d}{'_scan' if scanned else ''}.pdf"

        r = requests.post(
            f"{a.api}/api/documents",
            files={"files": (name, pdf, "application/pdf")},
            data={"institution": inst, "doc_date": d.isoformat()},
            timeout=60,
        )
        r.raise_for_status()
        ok += 1
        print(f"[{i:03d}/{a.count}] {name:28s} {inst}")
    print(f"Selesai: {ok} dokumen diunggah. Pantau proses di dashboard.")


if __name__ == "__main__":
    main()
