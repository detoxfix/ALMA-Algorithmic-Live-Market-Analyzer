"""Bobot portofolio per horizon.

bobot_mentah_i = skor_i / volatilitas_i (ATR%)   -> keyakinan tinggi & volatilitas rendah dapat porsi lebih besar
lalu dinormalisasi, dibatasi `max_weight` per saham (water-filling) dan `sector_cap` per sektor.
Sisa yang tidak teralokasi = KAS. Jumlah saham juga dibatasi aturan risiko `risk_per_trade`.
Saham AS tidak memakai lot: jumlah dibulatkan ke lembar utuh atau pecahan (fractional) sesuai broker.
"""
from __future__ import annotations

import numpy as np

from .ranking import rank_value
from .utils import qty_floor


def _water_fill(raw: np.ndarray, cap: float) -> np.ndarray:
    w = raw / raw.sum()
    capped = np.zeros(len(w), dtype=bool)
    for _ in range(len(w) + 1):
        over = (w > cap + 1e-12) & ~capped
        if not over.any():
            break
        capped |= over
        w[capped] = cap
        free = ~capped
        remaining = 1 - cap * capped.sum()
        if not free.any() or remaining <= 0:
            break
        w[free] = remaining * raw[free] / raw[free].sum()
    return w


def allocate(picks: list[dict], hcfg: dict, capital: float, risk_per_trade: float,
             scale: float = 1.0) -> tuple[list[dict], float]:
    """picks: kandidat BUY (sudah ada score, atr_pct, sector, entry, sl). Return (picks berbobot, kas).
    scale < 1 memperkecil seluruh bobot (mis. saat S&P 500 bearish); sisanya menjadi kas."""
    rank = hcfg.get("rank") or "score"            # urutan saat sinyal melebihi kuota (sama dengan backtest)
    picks = sorted(picks, key=lambda p: rank_value(rank, p["score"], p.get("atr_pct"), p.get("rs_60"),
                                                   p.get("ticker", p.get("code", "")), p.get("date", "")))
    picks = picks[: hcfg["max_positions"]]
    if not picks:
        return [], 1.0
    raw = np.array([max(p["score"], 1) / max(p.get("atr_pct") or 0.03, 0.005) for p in picks], dtype=float)
    w = _water_fill(raw, hcfg["max_weight"])

    # batas per sektor
    sectors: dict[str, float] = {}
    for p, wi in zip(picks, w):
        sectors[p["sector"]] = sectors.get(p["sector"], 0) + wi
    for i, p in enumerate(picks):
        tot = sectors[p["sector"]]
        if tot > hcfg["sector_cap"]:
            w[i] *= hcfg["sector_cap"] / tot

    w = w * max(0.0, min(1.0, scale))
    bucket = capital * hcfg["allocation"]
    for p, wi in zip(picks, w):
        entry, sl = p["entry"], p["sl"]
        q_w = bucket * wi / entry
        per_share_risk = max(entry - sl, 1e-9)
        q_r = capital * risk_per_trade / per_share_risk
        qty = qty_floor(min(q_w, q_r))
        p["weight_bucket"] = float(wi)                       # bobot di dalam bucket horizon
        p["weight_total"] = float(wi * hcfg["allocation"])   # bobot terhadap total modal
        p["shares"] = qty
        p["position_value"] = float(qty * entry)
        p["max_loss_value"] = float(qty * per_share_risk)
        p["shares_limited_by_risk"] = bool(q_r < q_w)
    cash = float(max(0.0, 1 - w.sum()))
    return picks, cash
