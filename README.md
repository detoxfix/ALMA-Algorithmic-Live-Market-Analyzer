# ALMA — Algorithmic Live Market Analyzer

Aplikasi rekomendasi **beli / jual** saham Amerika Serikat untuk anggota **S&P 500** berkapitalisasi pasar
**≥ US$10 miliar**, dengan tiga horizon (pendek, menengah, panjang). Turunan dari
[PANDU](https://github.com/detoxfix/analisis-market) (IHSG): mesin skor, rencana trading, bobot, backtest,
track record, alarm, dan usulan parameter sama; data, aturan pasar, dan mata uang disesuaikan untuk bursa AS.

Setiap pagi setelah bursa AS tutup, ALMA mengunduh data terbaru, menghitung skor, lalu menerbitkan dashboard:

- **Sinyal** STRONG BUY / BUY / HOLD / SELL / STRONG SELL + skor −100…+100
- **Kapan beli**: area beli (entry) dan batas kejar
- **Kapan jual**: TP1, TP2, cut loss, aturan trailing & time-stop
- **Berapa lama hold**: 3–10 hari bursa · 1–3 bulan · 6–24 bulan
- **Bobot (weight)** per saham terhadap total modal + jumlah saham (boleh pecahan), dalam USD dan setara Rupiah
- **Track record** otomatis atas setiap rekomendasi, dan **backtest** aturan sinyal

> ⚠️ Alat bantu analisis, **bukan nasihat investasi**. Selalu cek ulang harga di aplikasi broker Anda.

---

## Status: parameter belum dituning untuk pasar AS

Angka di `config.yaml` adalah titik awal, **bukan** salinan hasil tuning IHSG. Setelah repo aktif, jalankan
workflow **Tuning strategi** dengan mode `full`, lalu tetapkan parameter pendek & menengah dari hasil
in-sample / out-of-sample (`docs/data/tuning.json`).

## Sumber data (gratis & terbuka, diperbarui harian)

| Data | Sumber | Keterangan |
|---|---|---|
| Harga OHLCV harian, jumlah saham, fundamental (PER, PBV, ROE, DER, dividen, pertumbuhan laba) | Yahoo Finance melalui **[yfinance](https://github.com/ranaroussi/yfinance)** | Library open source (Apache-2.0). S&P 500 = `^GSPC`; kode bertitik memakai tanda hubung di Yahoo (BRK.B → `BRK-B`) |
| Anggota S&P 500 sekarang + tanggal masuk/keluar indeks | **[fja05680/sp500](https://github.com/fja05680/sp500)** (MIT) | Bersumber dari Wikipedia; cadangan di `data/sp500_seed/` bila unduhan gagal |
| Kurs USD/IDR | Yahoo Finance (`IDR=X`) | Hanya untuk tampilan setara Rupiah |

Catatan jujur: Yahoo bukan penyedia data berlisensi — data bisa terlambat, kosong, atau berubah format. Daftar
keanggotaan indeks diperbarui berkala oleh pengelolanya, jadi perubahan indeks beberapa minggu terakhir bisa
belum tercatat.

## Filter universe

1. Anggota S&P 500 (pada tanggal itu, untuk backtest)
2. Market cap = jumlah saham × harga penutupan terakhir **≥ US$10.000.000.000** (`universe.min_market_cap`)
3. Rata-rata nilai transaksi 20 hari ≥ US$50 juta, harga ≥ US$5, masih diperdagangkan

## Perbedaan utama dari PANDU

| Bagian | PANDU (IHSG) | ALMA (AS) |
|---|---|---|
| Daftar saham | idx.co.id | S&P 500, termasuk mantan anggota untuk backtest per tanggal |
| Pembanding pasar | ^JKSE | ^GSPC |
| Fraksi harga / lot | Rp1–25, 100 lembar | $0,01 (di bawah $1: $0,0001), 1 lembar atau pecahan |
| Batas harian | ARA/ARB disimulasikan | tidak ada; gap menembus cut loss dijual di harga pembukaan |
| Slippage backtest | dalam tick | dalam basis poin (cut loss 5 bp, lelang buka/tutup 2 bp) |
| Biaya | broker BEI | `fees.buy` / `fees.sell` sesuai broker AS Anda (+ catatan selisih kurs) |
| Jadwal | 17:30 WIB, Senin–Jumat | 05:30 WIB, Selasa–Sabtu |
| Mata uang | Rupiah | USD, ditampilkan juga setara Rupiah |
| Data khusus | transaksi asing IDX | tidak ada; sektor memakai klasifikasi GICS resmi indeks |

## Cara menjalankan

```bash
pip install -r requirements.txt
python main.py --demo            # uji coba offline (data sintetis)
python main.py                   # data asli, butuh internet
python main.py --backtest always # paksa backtest ulang
python -m pytest -q              # uji unit
```

Hasil:
- `docs/index.html` — dashboard (buka langsung di browser)
- `docs/data/latest.json` — semua sinyal (untuk integrasi lain)
- `docs/data/history/signals_YYYY-MM-DD.json` — arsip harian
- `docs/data/recommendations.csv` — catatan & hasil setiap rekomendasi
- `output/signals_latest.csv` — tabel sinyal untuk Excel

## Update otomatis setiap hari (gratis)

**GitHub Actions + GitHub Pages**
1. *Settings → Pages* → Source: `Deploy from a branch`, branch `main`, folder `/docs`.
2. *Settings → Secrets and variables → Actions* → isi `TELEGRAM_BOT_TOKEN` (boleh bot yang sama dengan PANDU)
   dan `TELEGRAM_CHAT_ID` (chat/grup khusus ALMA). Opsional: `POSITIONS_CSV` (lihat di bawah).
3. *Actions* → jalankan **Tuning strategi** mode `full` sekali, lalu sesuaikan `config.yaml`.
4. Workflow **Update sinyal saham AS harian** berjalan otomatis 05:30 WIB Selasa–Sabtu (22:30 UTC Senin–Jumat),
   atau klik *Run workflow*.
5. Dashboard tersedia di `https://detoxfix.github.io/ALMA-Algorithmic-Live-Market-Analyzer/`.

## Aplikasi laptop (Windows)

Tombol **Update sekarang**, **Buka dashboard**, **Posisi saya**, **Usulan**, **Pengaturan** (modal USD,
Telegram), dan jadwal otomatis Selasa–Sabtu 05:30 WIB lewat Windows Task Scheduler.

Membuat `.exe`: jalankan workflow **Build aplikasi Windows** → unduh artifact `ALMA-Windows` → ekstrak →
jalankan `ALMA.exe` (lihat `packaging/CARA PAKAI.txt`). Dari kode: `python app.py` atau `python app.py --auto`.

## Pemantau posisi pribadi

Repo ini publik, jadi **`positions.csv` tidak pernah di-commit** (sudah di `.gitignore`). Dua cara memakainya:

- **Aplikasi laptop**: isi lewat tombol **Posisi saya** (tersimpan di folder aplikasi).
- **GitHub Actions**: simpan isi CSV sebagai secret `POSITIONS_CSV`. Workflow menulisnya ke file sementara,
  menjalankan analisis, lalu menghapusnya sebelum commit.

```
code,horizon,buy_date,buy_price,shares,tp1_done,sl,tp1,tp2,note
AAPL,pendek,2026-10-29,227.50,4,,,,,
MSFT,menengah,2026-10-29,512.30,1.25,ya,,,,
```

- `horizon`: pendek / menengah / panjang · `shares` boleh pecahan · `tp1_done`: isi `ya` setelah menjual separuh
- `sl`, `tp1`, `tp2` opsional — kosongkan untuk memakai level hitungan aplikasi

Dashboard publik tidak menampilkan jumlah saham & nominal (`positions.dashboard: percent`); Telegram selalu lengkap.

## Metodologi singkat

Skor tiap horizon = rata-rata berbobot komponen bernilai −1…+1, dikali 100.

| Horizon | Komponen (bobot) |
|---|---|
| **Pendek** (3–10 hari) | Harga vs EMA20 (20) · EMA9 vs EMA20 (15) · momentum MACD (15) · zona RSI (15) · lonjakan volume naik/turun (15) · breakout/breakdown 20 hari (10) · S&P 500 vs EMA20 (10) |
| **Menengah** (1–3 bulan) | Harga vs SMA50 (15) · SMA50>SMA100 & menanjak (15) · ADX/DMI (15) · return 3 bulan (15) · kekuatan relatif vs S&P 500 (15) · rezim RSI (10) · MACD vs sinyal & nol (15) |
| **Panjang** (6–24 bulan) | Harga vs SMA200 (15) · kemiringan SMA200 (10) · momentum 12-1 bulan (15) · ROE (15) · PER relatif sektor (10) · PBV relatif sektor (10) · DER (10, tidak untuk sektor keuangan) · dividend yield (5) · pertumbuhan laba (10) |

**Ambang sinyal:** ≥ 60 STRONG BUY · ≥ 30 BUY · ≤ −30 SELL · ≤ −60 STRONG SELL · lainnya HOLD.

**Bobot portofolio:** modal dibagi ke bucket (pendek 20%, menengah 30%, panjang 50%). Di tiap bucket, bobot ∝
skor ÷ ATR%, dibatasi bobot maks. per saham & per sektor GICS; sisanya **kas**. Jumlah saham dibatasi agar rugi
per posisi ≤ 1% modal.

**Sinyal jual** ditujukan untuk pemegang saham (tanpa short selling).

## Backtest jujur

- **Universe per tanggal**: saham hanya boleh dibeli pada hari ia anggota S&P 500 dan lolos batas market cap &
  likuiditas hari itu. Mantan anggota indeks yang datanya masih ada di Yahoo ikut diuji.
- **Eksekusi**: slippage (basis poin), limit order baru terisi bila harga menembus $0,01, biaya beli & jual.
- **In-sample / out-of-sample**: parameter dipilih dari data sebelum `backtest.split_date` (1 Nov 2024),
  diuji sesudahnya.
- **Sisa bias**: saham yang sudah delisting (diakuisisi/bangkrut) tidak ada di data gratis; jumlah saham beredar
  memakai angka terkini. Anggap hasil backtest sedikit optimistis.

## Belajar dari kesalahan (dengan persetujuan Anda)

- **Alarm penyimpangan** (`src/monitor.py`): hasil rekomendasi sungguhan dibandingkan sebaran hasil backtest.
  Status: BELUM CUKUP DATA · NORMAL · LEBIH BAIK · WASPADA · BAHAYA. Tidak mengubah apa pun.
- **Usulan parameter bulanan** (`python tune.py --propose`, otomatis tanggal 1): satu perubahan dipilih dari data
  sebelum 6 bulan terakhir, harus tetap lebih baik di 6 bulan terakhir dan di simulasi portofolio. Diterapkan
  hanya lewat tombol **Usulan → Terapkan** di aplikasi atau dengan mengubah `config.yaml`.

## Struktur proyek

```
main.py                 orkestrasi harian
tune.py                 tuning & usulan parameter
app.py                  aplikasi Windows (Tkinter)
config.yaml             parameter
src/loader.py           satu pintu pengambilan data pasar
src/sp500.py            anggota S&P 500 sekarang & riwayat
src/data.py             yfinance (harga, jumlah saham, fundamental, kurs) + data demo
src/universe.py         filter S&P 500 ≥ US$10 miliar, likuiditas, universe per tanggal
src/indicators.py       EMA/SMA/RSI/MACD/ATR/ADX/volume/momentum
src/signals.py          skor & sinyal 3 horizon + alasan
src/risk.py             area beli, TP, SL, lama hold
src/portfolio.py        bobot & jumlah saham
src/sim.py              simulasi transaksi (track record & backtest)
src/backtest.py         backtest per transaksi
src/portsim.py          simulasi portofolio
src/tracker.py          catatan kinerja rekomendasi riil
src/monitor.py          alarm penyimpangan
src/positions.py        pemantau posisi pribadi
src/report.py           dashboard HTML
src/notify.py           Telegram
.github/workflows/      update harian, tuning, build Windows
tests/test_core.py      uji unit
```
