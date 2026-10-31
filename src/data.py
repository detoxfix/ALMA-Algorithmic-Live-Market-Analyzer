"""Pengambilan data harian dari sumber terbuka/publik.

Sumber:
  1. Harga OHLCV, jumlah saham, fundamental, kurs USD/IDR -> Yahoo Finance via `yfinance`
     (library open source, lisensi Apache-2.0; data publik gratis)
  2. Anggota S&P 500 (sekarang & riwayat)               -> src/sp500.py
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from .utils import ROOT, dump_json, fnum, load_json, log

CACHE = ROOT / "data" / "cache"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")


def ysym(code: str) -> str:
    """Kode saham -> simbol Yahoo (BRK.B -> BRK-B). Indeks (^GSPC) dan kurs (IDR=X) tidak diubah."""
    code = str(code).strip().upper()
    return code if code.startswith("^") or code.endswith("=X") else code.replace(".", "-")


def code_of(ticker: str) -> str:
    """Simbol Yahoo -> kode saham seperti tertulis di bursa (BRK-B -> BRK.B)."""
    return str(ticker).replace("-", ".")


# ------------------------------------------------------------------ harga
def _normalize(sub: pd.DataFrame) -> pd.DataFrame | None:
    cols = ["Open", "High", "Low", "Close", "Volume"]
    if not set(cols).issubset(sub.columns):
        return None
    sub = sub[cols].dropna(subset=["Open", "High", "Low", "Close"]).copy()
    idx = pd.to_datetime(sub.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    sub.index = idx.normalize()
    sub = sub[~sub.index.duplicated(keep="last")].sort_index()
    sub["Volume"] = sub["Volume"].fillna(0)
    return sub if len(sub) >= 60 else None


def download_prices(tickers: list[str], period: str = "3y", chunk: int = 60) -> dict[str, pd.DataFrame]:
    import yfinance as yf

    out: dict[str, pd.DataFrame] = {}
    tickers = [ysym(t) for t in tickers]
    for i in range(0, len(tickers), chunk):
        batch = tickers[i:i + chunk]
        raw = None
        for attempt in range(4):
            try:
                raw = yf.download(batch, period=period, interval="1d", auto_adjust=True,
                                  group_by="ticker", threads=True, progress=False)
                break
            except Exception as e:  # noqa: BLE001  (rate limit dsb.)
                wait = 10 * (attempt + 1)
                log.warning("Unduh batch %d gagal (%s), coba lagi %ds", i // chunk + 1, e, wait)
                time.sleep(wait)
        if raw is None or raw.empty:
            continue
        for t in batch:
            try:
                sub = raw[t] if isinstance(raw.columns, pd.MultiIndex) else raw
            except KeyError:
                continue
            norm = _normalize(sub)
            if norm is not None:
                out[t] = norm
        log.info("Harga: batch %d/%d selesai (%d ticker valid)", i // chunk + 1,
                 (len(tickers) - 1) // chunk + 1, len(out))
        time.sleep(1.0)
    return out


def usd_idr(default: float | None = None) -> tuple[float | None, str | None]:
    """Kurs USD/IDR penutupan terakhir dari Yahoo (simbol IDR=X), di-cache. Return (kurs, tanggal)."""
    path = CACHE / "fx.json"
    try:
        import yfinance as yf
        raw = yf.download("IDR=X", period="1mo", interval="1d", auto_adjust=True, progress=False)
        c = raw["Close"]
        c = (c.iloc[:, 0] if isinstance(c, pd.DataFrame) else c).dropna()
        c = c[(c > 5000) & (c < 50000)]              # buang angka rusak
        if len(c):
            rate, day = float(c.iloc[-1]), pd.Timestamp(c.index[-1]).strftime("%Y-%m-%d")
            dump_json({"usd_idr": rate, "date": day}, path)
            return rate, day
    except Exception as e:  # noqa: BLE001
        log.warning("Kurs USD/IDR gagal diunduh (%s), memakai cache", e.__class__.__name__)
    c = load_json(path, {}) or {}
    return (c.get("usd_idr") or default), c.get("date")


# ------------------------------------------------------------------ jumlah saham & fundamental
def _fresh(entry: dict | None, days: int) -> bool:
    if not entry or "ts" not in entry:
        return False
    try:
        return datetime.fromisoformat(entry["ts"]) > datetime.now() - timedelta(days=days)
    except ValueError:
        return False


def get_shares(tickers: list[str], max_age_days: int = 7) -> dict[str, float]:
    """Jumlah saham beredar (fast_info), di-cache mingguan."""
    import yfinance as yf

    path = CACHE / "shares.json"
    cache = load_json(path, {}) or {}
    todo = [t for t in tickers if not _fresh(cache.get(t), max_age_days)]
    if todo:
        log.info("Ambil jumlah saham %d ticker (cache %d)", len(todo), len(tickers) - len(todo))
    for n, t in enumerate(todo, 1):
        shares = None
        try:
            fi = yf.Ticker(t).fast_info
            try:
                shares = fi["shares"]
            except Exception:  # noqa: BLE001
                shares = getattr(fi, "shares", None)
        except Exception:  # noqa: BLE001
            pass
        if fnum(shares):
            cache[t] = {"shares": float(shares), "ts": datetime.now().isoformat(timespec="seconds")}
        if n % 25 == 0:
            dump_json(cache, path)
            time.sleep(1)
    dump_json(cache, path)
    return {t: cache[t]["shares"] for t in tickers if t in cache}


FUND_VERSION = 3


def _clean_fund(f: dict) -> dict:
    """Saring nilai fundamental Yahoo yang tidak masuk akal.

    - PBV: negatif (ekuitas negatif karena buyback, mis. beberapa saham konsumer) atau di atas 200x
      -> tidak tersedia (tidak bermakna untuk perbandingan sektor).
    - PER: di atas 500x atau negatif ekstrem -> tidak tersedia.
    - Dividend yield: yfinance >= 0.2.54 memberi angka PERSEN (7,7 = 7,7%) -> selalu dibagi 100.
    """
    f = dict(f)
    pb, pe = f.get("pb"), f.get("pe")
    if pb is not None and (pb <= 0 or pb > 200):
        f["pb"] = None
    if pe is not None and (pe > 500 or pe < -500):
        f["pe"] = None
    dy = f.get("div_yield_raw")
    f["div_yield"] = dy / 100 if dy is not None else None
    if f["div_yield"] is not None and f["div_yield"] > 0.20:   # >20% hampir pasti data salah
        f["div_yield"] = None
    return f


def get_fundamentals(tickers: list[str], max_age_days: int = 7) -> dict[str, dict]:
    import yfinance as yf

    path = CACHE / "fundamentals.json"
    cache = load_json(path, {}) or {}
    todo = [t for t in tickers if not _fresh(cache.get(t), max_age_days)
            or cache[t].get("v") != FUND_VERSION]
    if todo:
        log.info("Ambil fundamental %d ticker (cache %d)", len(todo), len(tickers) - len(todo))
    for n, t in enumerate(todo, 1):
        try:
            info = yf.Ticker(t).info or {}
        except Exception as e:  # noqa: BLE001
            log.debug("info %s gagal: %s", t, e)
            continue
        der = fnum(info.get("debtToEquity"))
        cache[t] = {
            "name": info.get("longName") or info.get("shortName"),
            "sector": info.get("sector") or "Other",
            "industry": info.get("industry"),
            "pe": fnum(info.get("trailingPE")),
            "pb": fnum(info.get("priceToBook")),
            "roe": fnum(info.get("returnOnEquity")),
            "der": der / 100 if der is not None else None,       # Yahoo: dalam persen
            "div_yield_raw": fnum(info.get("dividendYield")),
            "eps_ttm": fnum(info.get("trailingEps")),
            "bvps": fnum(info.get("bookValue")),
            "fin_currency": info.get("financialCurrency"),
            "v": FUND_VERSION,
            "eps_growth": fnum(info.get("earningsGrowth")),
            "rev_growth": fnum(info.get("revenueGrowth")),
            "shares": fnum(info.get("sharesOutstanding")),
            "ts": datetime.now().isoformat(timespec="seconds"),
        }
        if n % 20 == 0:
            dump_json(cache, path)
        time.sleep(0.4)
    dump_json(cache, path)
    return {t: _clean_fund(cache[t]) for t in tickers if t in cache}


# ------------------------------------------------------------------ mode demo (offline)
def demo_dataset(n: int = 45, days: int = 1000, seed: int = 7):
    """Data sintetis untuk uji coba tanpa internet. BUKAN data pasar asli."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days)
    sectors = ["Technology", "Financial Services", "Healthcare", "Consumer Cyclical", "Industrials",
               "Communication Services", "Consumer Defensive", "Energy"]
    market = np.cumsum(rng.normal(0.0004, 0.010, days))
    prices, funds, shares = {}, {}, {}
    for i in range(n):
        beta = rng.uniform(0.6, 1.5)
        drift = rng.normal(0.0002, 0.0006)
        vol = rng.uniform(0.010, 0.028)
        regime = np.repeat(rng.normal(0, 0.0015, days // 60 + 1), 60)[:days]
        r = beta * np.diff(np.r_[0, market]) + drift + regime + rng.normal(0, vol, days)
        p0 = rng.choice([25, 60, 110, 180, 320, 550, 900])
        close = p0 * np.exp(np.cumsum(r))
        openp = close * np.exp(rng.normal(0, vol / 3, days))
        high = np.maximum(openp, close) * (1 + np.abs(rng.normal(0, vol / 2, days)))
        low = np.minimum(openp, close) * (1 - np.abs(rng.normal(0, vol / 2, days)))
        volu = rng.lognormal(15, 0.5, days) * (1 + 3 * (np.abs(r) > 2 * vol))
        t = f"DM{i + 1:02d}"
        prices[t] = pd.DataFrame({"Open": openp, "High": high, "Low": low, "Close": close,
                                  "Volume": volu.round()}, index=dates)
        shares[t] = float(rng.uniform(1e8, 6e9))
        sec = sectors[i % len(sectors)]
        funds[t] = {"name": f"Demo Corp {i + 1:02d}", "sector": sec, "industry": None,
                    "pe": float(rng.uniform(8, 45)), "pb": float(rng.uniform(1, 15)),
                    "roe": float(rng.uniform(-0.05, 0.4)),
                    "der": float(rng.uniform(0.1, 2.5)) if sec != "Financial Services" else None,
                    "div_yield": float(rng.uniform(0, 0.04)), "eps_growth": float(rng.normal(0.08, 0.2)),
                    "rev_growth": None, "shares": shares[t]}
    bench = pd.Series(5000 * np.exp(market), index=dates, name="^GSPC")
    return prices, bench, shares, funds
