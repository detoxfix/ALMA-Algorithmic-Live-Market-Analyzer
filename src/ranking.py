"""Urutan prioritas saat sinyal BUY lebih banyak dari kuota posisi (opsi `rank` per horizon).

Nilai lebih KECIL = dipilih lebih dulu. Dipakai sama persis oleh rekomendasi harian (portfolio.allocate)
dan simulasi portofolio (portsim), agar backtest menguji aturan yang benar-benar dipakai.

  score      skor tertinggi dulu (cara lama)
  low_score  skor terendah yang masih lolos ambang dulu (saham yang belum terlalu "panas")
  low_vol    volatilitas (ATR%) terendah dulu
  rs         kekuatan relatif 3 bulan vs S&P 500 tertinggi dulu
  random     acak tetapi dapat diulang (hash kode + tanggal) — pembanding netral
"""
from __future__ import annotations

import math
import zlib

RANKS = ("score", "low_score", "low_vol", "rs", "random")


def _f(x, default):
    try:
        v = float(x)
        return v if math.isfinite(v) else default
    except (TypeError, ValueError):
        return default


def rank_value(rank: str, score, atr_pct=None, rs=None, ticker: str = "", date: str = "") -> float:
    rank = rank or "score"
    if rank == "low_score":
        return _f(score, 1e9)
    if rank == "low_vol":
        return _f(atr_pct, 1e9)
    if rank == "rs":
        return -_f(rs, -1e9)
    if rank == "random":
        return zlib.crc32(f"{ticker}|{str(date)[:10]}".encode()) / 2**32
    return -_f(score, -1e9)
