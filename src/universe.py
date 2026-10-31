"""Penyaringan universe: anggota S&P 500, kapitalisasi pasar >= US$10 miliar, likuid, masih diperdagangkan."""
from __future__ import annotations

import pandas as pd

from . import sp500
from .data import code_of, ysym
from .utils import log


def candidate_list(cfg: dict, hist: pd.DataFrame | None = None,
                   since: pd.Timestamp | None = None) -> tuple[list[str], list[str], dict, dict]:
    """Return (tickers_sekarang, tickers_mantan_anggota, names, sectors). Ticker = simbol Yahoo.
    Mantan anggota (keluar sejak `since`) hanya untuk backtest per tanggal."""
    ucfg = cfg["universe"]
    exclude = {c.upper() for c in ucfg.get("exclude", [])}
    cur = sp500.current()
    cur = cur[~cur["code"].isin(exclude)]
    names = {ysym(r.code): r.name for r in cur.itertuples(index=False)}
    sectors = {ysym(r.code): r.sector for r in cur.itertuples(index=False)}
    tickers = sorted(names)
    former: list[str] = []
    if hist is not None and since is not None:
        former = sorted({ysym(c) for c in sp500.members_since(hist, since) if c not in exclude} - set(tickers))
    log.info("Kandidat: %d anggota S&P 500 sekarang (+%d mantan anggota untuk backtest)", len(tickers), len(former))
    return tickers, former, names, sectors


def filter_universe(prices: dict[str, pd.DataFrame], shares: dict[str, float], cfg: dict,
                    as_of: pd.Timestamp, current: set[str] | None = None) -> pd.DataFrame:
    """Market cap = jumlah saham x harga penutupan terakhir, lalu saring. `current` = anggota indeks hari ini."""
    u = cfg["universe"]
    rows = []
    for t, df in prices.items():
        last = df.index[-1]
        close = float(df["Close"].iloc[-1])
        val20 = float((df["Close"] * df["Volume"]).tail(20).mean())
        sh = shares.get(t)
        mcap = sh * close if sh else None
        stale = (as_of - last).days
        reason = None
        if current is not None and t not in current:
            reason = "bukan anggota S&P 500 saat ini"
        elif mcap is None:
            reason = "jumlah saham tidak tersedia"
        elif mcap < u["min_market_cap"]:
            reason = "market cap < batas"
        elif stale > u["max_stale_days"]:
            reason = f"tidak aktif {stale} hari (halt/delisting?)"
        elif val20 < u["min_avg_value_20d"]:
            reason = "kurang likuid"
        elif close < u["min_price"]:
            reason = "harga di bawah minimum"
        rows.append({"ticker": t, "code": code_of(t), "close": close, "mcap": mcap,
                     "avg_value_20d": val20, "last_date": last, "excluded": reason})
    uni = pd.DataFrame(rows)
    if uni.empty:
        return uni
    kept = uni[uni["excluded"].isna()].sort_values("mcap", ascending=False)
    log.info("Universe akhir: %d saham lolos (dari %d) | market cap >= US$%.0f miliar",
             len(kept), len(uni), u["min_market_cap"] / 1e9)
    return kept.reset_index(drop=True)


def eligibility(df: pd.DataFrame, shares: float | None, cfg: dict, member: pd.Series | None = None) -> pd.Series:
    """Lolos/tidaknya saham masuk universe PADA SETIAP TANGGAL (backtest tanpa melihat masa depan):
    anggota S&P 500 hari itu, market cap (jumlah saham x harga hari itu), likuiditas 20 hari, harga minimum.
    Jumlah saham memakai data terkini (perubahan karena buyback/emisi tidak terlacak)."""
    u = cfg["universe"]
    if not shares:
        return pd.Series(False, index=df.index)
    close = df["Close"]
    val20 = (close * df["Volume"]).rolling(20, min_periods=15).mean()
    ok = (close * shares >= u["min_market_cap"]) & (val20 >= u["min_avg_value_20d"]) & (close >= u["min_price"])
    if member is not None:
        ok = ok & member.reindex(df.index).fillna(False).astype(bool)
    return ok.fillna(False)


def backtest_set(prices: dict[str, pd.DataFrame], shares: dict[str, float], cfg: dict, current: list[str],
                 build, hist: pd.DataFrame | None = None) -> dict[str, pd.DataFrame]:
    """Saham untuk backtest: SEMUA saham yang pernah lolos syarat universe pada tanggal mana pun dalam
    riwayat (termasuk mantan anggota S&P 500 yang datanya masih ada). Kolom ELIG menandai hari saham
    itu boleh dibeli. `build(ticker)` mengembalikan DataFrame indikator (dipakai ulang bila sudah dihitung)."""
    out = {}
    for t, df in prices.items():
        member = None
        if hist is not None:
            member = pd.Series(sp500.member_mask(hist, code_of(t), df.index), index=df.index)
        el = eligibility(df, shares.get(t), cfg, member)
        if not el.any():
            continue
        d = build(t)
        d["ELIG"] = el.reindex(d.index).fillna(False).astype(bool)
        d.attrs["current"] = t in current           # lolos universe hari ini (untuk pembanding cara lama)
        out[t] = d
    extra = sorted(set(out) - set(current))
    gone = sorted(set(current) - set(out))
    log.info("Universe backtest per tanggal: %d saham (%d tidak lolos hari ini tapi pernah lolos%s)",
             len(out), len(extra), f"; {len(gone)} tanpa data jumlah saham" if gone else "")
    return out
