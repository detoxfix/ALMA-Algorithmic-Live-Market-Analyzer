"""Satu pintu pengambilan data pasar (dipakai main.py, tune.py, dan aplikasi Windows)."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from . import data as D
from . import sp500
from .universe import candidate_list
from .utils import log


@dataclass
class Market:
    prices: dict[str, pd.DataFrame]
    bench: pd.Series | None
    shares: dict[str, float]
    names: dict[str, str]
    sectors: dict[str, str]
    current: set[str]                      # anggota S&P 500 hari ini (simbol Yahoo)
    hist: pd.DataFrame | None              # riwayat keanggotaan (None di mode demo)
    funds: dict[str, dict] | None = None   # hanya mode demo (fundamental sintetis)
    sources: list[str] = field(default_factory=list)


def period_start(period: str) -> pd.Timestamp:
    """'5y' / '3y' / '18mo' -> tanggal awal riwayat."""
    p = period.strip().lower()
    now = pd.Timestamp.today().normalize()
    if p.endswith("mo"):
        return now - pd.DateOffset(months=int(p[:-2]))
    if p.endswith("y"):
        return now - pd.DateOffset(years=int(p[:-1]))
    return now - pd.DateOffset(years=5)


def load(cfg: dict, demo: bool = False, former: bool = True, extra: list[str] | None = None) -> Market:
    """former=True: ikut unduh mantan anggota S&P 500 dalam periode riwayat (untuk backtest per tanggal).
    extra: kode tambahan (mis. saham di posisi pribadi yang bukan anggota indeks)."""
    if demo:
        log.warning("MODE DEMO: data sintetis, bukan data pasar asli!")
        prices, bench, shares, funds = D.demo_dataset()
        return Market(prices, bench, shares, {t: f["name"] for t, f in funds.items()},
                      {t: f["sector"] for t, f in funds.items()}, set(prices), None, funds,
                      ["DEMO — data sintetis"])
    dcfg = cfg["data"]
    hist = sp500.history()
    since = period_start(dcfg["history_period"])
    tickers, ex_members, names, sectors = candidate_list(cfg, hist, since if former else None)
    srcs = ["Anggota S&P 500 (sekarang & riwayat masuk/keluar): github.com/fja05680/sp500 (MIT), "
            "bersumber dari Wikipedia"]
    bpx = D.download_prices([dcfg["benchmark"]], period=dcfg["history_period"])
    bench = bpx[dcfg["benchmark"]]["Close"] if bpx else None
    want = tickers + ex_members + [D.ysym(c) for c in (extra or []) if D.ysym(c) not in names]
    prices = D.download_prices(sorted(set(want)), period=dcfg["history_period"])
    if ex_members:
        got = sum(1 for t in ex_members if t in prices)
        log.info("Mantan anggota: %d dari %d masih punya data harga di Yahoo", got, len(ex_members))
        srcs.append(f"Mantan anggota S&P 500 sejak {since:%Y}: {got} dari {len(ex_members)} masih ada datanya "
                    "(sisanya delisting/ganti kode — sisa bias survivorship)")
    shares = D.get_shares(list(prices), dcfg["shares_cache_days"])
    srcs.append("Harga OHLCV harian, jumlah saham, fundamental & kurs USD/IDR: Yahoo Finance via yfinance "
                "(open source, Apache-2.0)")
    return Market(prices, bench, shares, names, sectors, set(tickers) & set(prices), hist, None, srcs)
