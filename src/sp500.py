"""Anggota indeks S&P 500: daftar sekarang + riwayat masuk/keluar (untuk backtest per tanggal).

Sumber terbuka: repo GitHub `fja05680/sp500` (lisensi MIT), diperbarui berkala oleh pengelolanya
dari halaman Wikipedia "List of S&P 500 companies" dan riwayat perubahan indeks sejak 1996.
  - sp500.csv                   : anggota sekarang (kode, nama, sektor GICS)
  - sp500_ticker_start_end.csv  : tanggal masuk & keluar tiap kode (end kosong = masih anggota)

Diunduh mingguan ke data/cache. Bila gagal, memakai salinan cadangan di data/sp500_seed/.
Catatan jujur: perubahan indeks yang terjadi setelah pembaruan terakhir repo itu belum tercatat,
dan saham yang sudah delisting (diakuisisi/bangkrut) tidak punya data harga gratis di Yahoo.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from io import StringIO

import numpy as np
import pandas as pd

from .utils import BUNDLE, ROOT, log

BASE = "https://raw.githubusercontent.com/fja05680/sp500/master/"
FILES = {"current": "sp500.csv", "history": "sp500_ticker_start_end.csv"}
CACHE = ROOT / "data" / "cache"
SEED = "data/sp500_seed"


def _get(kind: str, max_age_days: int = 7) -> pd.DataFrame:
    name = FILES[kind]
    path = CACHE / f"sp500_{kind}.csv"
    fresh = path.exists() and datetime.fromtimestamp(path.stat().st_mtime) > datetime.now() - timedelta(days=max_age_days)
    if not fresh:
        try:
            import requests
            r = requests.get(BASE + name, timeout=30)
            r.raise_for_status()
            df = pd.read_csv(StringIO(r.text))
            if len(df) >= 400:                       # sanity check
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(r.text, encoding="utf-8")
                return df
            log.warning("Daftar S&P 500 (%s) hanya %d baris, diabaikan", kind, len(df))
        except Exception as e:  # noqa: BLE001
            log.warning("Unduh daftar S&P 500 (%s) gagal: %s", kind, e.__class__.__name__)
    for p in (path, ROOT / SEED / name, BUNDLE / SEED / name):
        if p.exists():
            log.info("Daftar S&P 500 (%s) dari %s", kind, p.parent.name)
            return pd.read_csv(p)
    raise SystemExit("Daftar S&P 500 tidak tersedia (unduhan gagal dan tidak ada cadangan).")


def current() -> pd.DataFrame:
    """Anggota sekarang: kolom code, name, sector (GICS)."""
    df = _get("current")
    return pd.DataFrame({"code": df["Symbol"].astype(str).str.strip().str.upper(),
                         "name": df["Security"].astype(str).str.strip(),
                         "sector": df["GICS Sector"].astype(str).str.strip()})


def history() -> pd.DataFrame:
    """Interval keanggotaan: kolom code, start, end (NaT = masih anggota). Satu kode bisa beberapa interval."""
    df = _get("history")
    return pd.DataFrame({"code": df["ticker"].astype(str).str.strip().str.upper(),
                         "start": pd.to_datetime(df["start_date"], errors="coerce"),
                         "end": pd.to_datetime(df["end_date"], errors="coerce")}).dropna(subset=["start"])


def members_since(hist: pd.DataFrame, since: pd.Timestamp) -> list[str]:
    """Semua kode yang menjadi anggota pada tanggal mana pun sejak `since` (termasuk yang sudah keluar)."""
    m = hist[hist["end"].isna() | (hist["end"] >= since)]
    return sorted(m["code"].unique())


def member_mask(hist: pd.DataFrame, code: str, dates: pd.DatetimeIndex) -> np.ndarray:
    """True pada tanggal saham `code` tercatat sebagai anggota S&P 500.
    Tanggal keluar dianggap hari pertama bukan anggota (efektif sebelum pembukaan)."""
    out = np.zeros(len(dates), dtype=bool)
    d = dates.values
    for r in hist[hist["code"] == code].itertuples(index=False):
        end = r.end if pd.notna(r.end) else pd.Timestamp.max
        out |= (d >= np.datetime64(r.start)) & (d < np.datetime64(end))
    return out
