"""Utilitas umum: logging, fraksi harga & jumlah saham pasar AS, format USD/IDR, JSON aman."""
from __future__ import annotations

import json
import logging
import math
import os
import sys
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

def _home() -> Path:
    """Folder kerja (data, dashboard, config, posisi).
    - ALMA_HOME (env) bila diisi
    - aplikasi .exe: folder tempat .exe berada (bila bisa ditulis), jika tidak %LOCALAPPDATA%\\ALMA
    - selain itu: folder proyek"""
    env = os.environ.get("ALMA_HOME")
    if env:
        return Path(env)
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
        try:
            probe = base / ".write_test"
            probe.write_text("x")
            probe.unlink()
            return base
        except OSError:
            return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ALMA"
    return Path(__file__).resolve().parent.parent


ROOT = _home()
BUNDLE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))   # file bawaan (read-only)

log = logging.getLogger("alma")
if not log.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s",
                        datefmt="%H:%M:%S")


def now_wib() -> datetime:
    """Waktu WIB tanpa info zona. Tidak bergantung database zona waktu (Windows tidak punya bawaan)."""
    from datetime import timedelta, timezone
    return datetime.now(timezone(timedelta(hours=7))).replace(tzinfo=None)


# ---------------------------------------------------------------- pasar AS: fraksi harga & jumlah saham
# Reg NMS Rule 612: harga >= $1 dikutip per $0,01; di bawah $1 per $0,0001.
# Tidak ada lot: 1 lembar, atau pecahan bila broker mendukung (diatur lewat set_market dari config.yaml).
MARKET = {"fractional": True, "qty_step": 0.0001, "usd_idr": None}


def set_market(cfg: dict):
    """Baca bagian `market` di config.yaml (dipanggil sekali di awal)."""
    m = (cfg or {}).get("market", {}) or {}
    MARKET["fractional"] = bool(m.get("fractional_shares", True))
    MARKET["qty_step"] = float(m.get("fractional_step", 0.0001)) if MARKET["fractional"] else 1.0


def tick_size(price: float) -> float:
    """Fraksi harga saham AS."""
    return 0.01 if price >= 1 else 0.0001


def round_tick(price: float, mode: str = "nearest") -> float:
    if price is None or not np.isfinite(price) or price <= 0:
        return float("nan")
    t = tick_size(price)
    n = price / t
    if mode == "down":
        k = math.floor(n + 1e-9)
    elif mode == "up":
        k = math.ceil(n - 1e-9)
    else:
        k = round(n)
    return float(round(max(k, 1) * t, 4))


def qty_floor(shares: float) -> float:
    """Bulatkan ke bawah jumlah saham yang bisa dibeli (lembar utuh, atau pecahan sesuai broker)."""
    if shares is None or not np.isfinite(shares) or shares <= 0:
        return 0.0
    step = MARKET["qty_step"]
    q = math.floor(shares / step + 1e-9) * step
    return float(round(q, 6)) if step < 1 else float(int(q))


def usd(x, d: int = 2) -> str:
    """$1,234.56 (pemisah gaya AS, karena harga di broker AS ditulis begitu)."""
    if x is None or not np.isfinite(x):
        return "-"
    return f"-${-x:,.{d}f}" if x < 0 else f"${x:,.{d}f}"


def px(x) -> str:
    """Harga saham tanpa simbol: 2 desimal (4 desimal di bawah $1)."""
    if x is None or not np.isfinite(x):
        return "-"
    return f"{x:,.2f}" if x >= 1 else f"{x:,.4f}"


def idr(x) -> str:
    """Rp 1.234.567 (setara Rupiah memakai kurs harian)."""
    if x is None or not np.isfinite(x):
        return "-"
    return "Rp " + f"{x:,.0f}".replace(",", ".")


# ---------------------------------------------------------------- JSON
def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return None if not math.isfinite(f) else round(f, 6)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (pd.Timestamp, datetime, date)):
        return o.strftime("%Y-%m-%d")
    if o is pd.NA or o is pd.NaT:
        return None
    return o


def dump_json(obj, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_clean(obj), ensure_ascii=False, indent=1), encoding="utf-8")


def to_jsonable(obj):
    return _clean(obj)


def load_json(path: Path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def fnum(x, default=None):
    """float aman: None / NaN -> default."""
    try:
        f = float(x)
        return f if math.isfinite(f) else default
    except (TypeError, ValueError):
        return default
