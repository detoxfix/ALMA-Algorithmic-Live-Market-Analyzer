"""Uji unit inti. Jalankan: python -m pytest -q  (atau: python tests/test_core.py)"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.portfolio import _water_fill, allocate  # noqa: E402
from src.risk import make_plan  # noqa: E402
from src.sim import simulate  # noqa: E402
from src.utils import MARKET, qty_floor, round_tick, set_market, tick_size  # noqa: E402

FEES = {"buy": 0.001, "sell": 0.001}


def test_tick_size():
    assert tick_size(227.5) == 0.01 and tick_size(0.85) == 0.0001
    assert round_tick(227.456, "down") == 227.45 and round_tick(227.451, "up") == 227.46
    assert round_tick(227.455, "nearest") in (227.45, 227.46) and round_tick(0.123456) == 0.1235


def test_quantity():
    set_market({"market": {"fractional_shares": True, "fractional_step": 0.0001}})
    assert qty_floor(3.14159) == 3.1415
    set_market({"market": {"fractional_shares": False}})
    assert qty_floor(3.99) == 3.0 and qty_floor(0.5) == 0.0
    set_market({})                             # kembali ke default (pecahan)
    assert MARKET["fractional"]


def test_plan_levels_valid():
    row = {"Close": 232.40, "ATR14": 4.10, "EMA20": 228.0, "SMA50": 220.0, "HH250": 260.0}
    h = {"entry_atr": 0.5, "chase_atr": 0.3, "sl_atr": 1.5, "max_sl_pct": 0.07, "rr": [1.5, 2.5],
         "hold_min_days": 3, "hold_max_days": 10}
    p = make_plan(row, "short", h, FEES)
    assert p["sl"] < p["entry_low"] <= p["entry"] <= p["entry_high"] < p["tp1"] < p["tp2"]
    for k in ("sl", "tp1", "tp2", "entry_low", "entry_high"):
        assert abs(p[k] * 100 - round(p[k] * 100)) < 1e-6, k          # kelipatan $0,01
    assert p["sl_pct"] >= -0.07 - 1e-9


def _bars(rows):
    idx = pd.bdate_range("2026-01-01", periods=len(rows))
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"], index=idx)


def test_sim_sl_and_tp():
    plan = {"entry_high": 1010, "sl": 950, "tp1": 1060, "tp2": 1100, "max_hold_days": 10}
    sl_case = _bars([[1000, 1000, 1000, 1000], [1000, 1010, 940, 945]])
    assert simulate(sl_case, 0, plan, FEES)["outcome"] == "SL"
    tp_case = _bars([[1000] * 4, [1000, 1070, 990, 1065], [1065, 1110, 1060, 1100]])
    r = simulate(tp_case, 0, plan, FEES)
    assert r["outcome"] == "TP2" and r["tp1_hit"] and r["ret"] > 0.07
    gap = _bars([[1000] * 4, [1050, 1060, 1040, 1050]])
    assert simulate(gap, 0, plan, FEES)["outcome"] == "BATAL"


def test_sim_limit_and_trail():
    plan = {"entry": 980, "entry_high": 980, "sl": 940, "tp1": 1020, "tp2": 1200, "max_hold_days": 10,
            "entry_mode": "limit", "limit_days": 3, "trail_ma": 0}
    miss = _bars([[1000] * 4, [1000, 1010, 990, 1000], [1000, 1010, 985, 1000], [1000, 1010, 990, 1000]])
    assert simulate(miss, 0, plan, FEES)["outcome"] == "BATAL"
    fill = _bars([[1000] * 4, [1000, 1010, 975, 990], [990, 1030, 985, 1025]])
    r = simulate(fill, 0, plan, FEES)
    assert r["entry_px"] == 980 and r["tp1_hit"]
    trail_plan = {**plan, "trail_ma": 2}
    rows = [[1000] * 4, [1000, 1010, 975, 990], [990, 1030, 985, 1025], [1025, 1026, 990, 991]]
    r2 = simulate(_bars(rows), 0, trail_plan, FEES)
    assert r2["outcome"] == "TP1+TRAIL", r2["outcome"]


def test_market_exit():
    from src.sim import market_flag
    assert market_flag([1, 0, 0, 1, 0], 1).tolist() == [False, True, True, False, True]
    assert market_flag([1, 0, 0, 1, 0], 2).tolist() == [False, False, True, False, False]
    plan = {"entry_high": 1010, "sl": 900, "tp1": 1100, "tp2": 1200, "max_hold_days": 20, "market_exit": "all"}
    rows = [[1000] * 4, [1000, 1010, 990, 1000], [1000, 1005, 980, 990], [990, 995, 950, 960]]
    import numpy as np
    from src.sim import simulate_arr
    o, h, l, c = (np.array([r[k] for r in rows], float) for k in range(4))
    flag = np.array([False, False, True, True])
    r = simulate_arr(o, h, l, c, 0, plan, FEES, None, flag)
    assert r["outcome"] == "MKT" and r["exit_px"] == 990
    r2 = simulate_arr(o, h, l, c, 0, {**plan, "market_exit": "half"}, FEES, None, flag)
    assert r2["outcome"].startswith("MKT½+") and r2["tp1_px"] == 990


def test_weights():
    w = _water_fill(np.array([10.0, 1, 1, 1]), 0.3)
    assert abs(w.sum() - 1) < 1e-9 and w.max() <= 0.3 + 1e-9
    picks = [{"score": 80, "atr_pct": 0.02, "sector": "A", "entry": 500.0, "sl": 475.0},
             {"score": 40, "atr_pct": 0.04, "sector": "A", "entry": 120.0, "sl": 112.8}]
    h = {"max_positions": 5, "max_weight": 0.6, "sector_cap": 0.5, "allocation": 0.2}
    out, cash = allocate(picks, h, 10_000, 0.01)
    assert abs(sum(p["weight_bucket"] for p in out) - 0.5) < 1e-9 and abs(cash - 0.5) < 1e-9
    assert all(p["max_loss_value"] <= 100 + 1e-6 for p in out)
    assert all(abs(p["position_value"] - p["shares"] * p["entry"]) < 1e-6 for p in out)
    assert out[0]["shares"] != int(out[0]["shares"])          # saham pecahan: $500 tidak perlu lembar utuh


def test_execution_realism():
    from src.sim import simulate_arr
    # beli di lelang pembukaan +2 bp; SL di tengah sesi 5 bp lebih buruk
    plan = {"entry_high": 101.0, "sl": 90.0, "tp1": 110.0, "tp2": 120.0, "max_hold_days": 20}
    rows = [[100.0] * 4, [100, 101, 99, 100], [99, 99.5, 88, 89]]
    o, h, l, c = (np.array([r[k] for r in rows], float) for k in range(4))
    r = simulate_arr(o, h, l, c, 0, plan, FEES, ex={"slip_bps": 5, "slip_auction_bps": 2, "through": True})
    assert abs(r["entry_px"] - 100.02) < 1e-9 and abs(r["exit_px"] - 90 * 0.9995) < 1e-9 and r["outcome"] == "SL"
    # TP yang hanya disentuh tidak terisi bila limit_through aktif (harus tembus $0,01)
    rows = [[100.0] * 4, [100, 101, 99, 100], [100, 110, 100, 105], [105, 111, 104, 110]]
    o, h, l, c = (np.array([r[k] for r in rows], float) for k in range(4))
    assert simulate_arr(o, h, l, c, 0, plan, FEES, ex={"through": True})["tp1_pos"] == 3
    assert simulate_arr(o, h, l, c, 0, plan, FEES)["tp1_pos"] == 2
    # gap turun menembus SL: tidak ada ARB di AS -> terjual di harga pembukaan hari itu
    rows = [[100.0] * 4, [100, 101, 99, 100], [85, 86, 80, 82]]
    o, h, l, c = (np.array([r[k] for r in rows], float) for k in range(4))
    r = simulate_arr(o, h, l, c, 0, plan, FEES)
    assert r["exit_pos"] == 2 and r["exit_px"] == 85


def test_point_in_time():
    from src.universe import eligibility
    idx_ = pd.date_range("2025-01-01", periods=40, freq="B")
    df = pd.DataFrame({"Close": np.r_[np.full(20, 100.0), np.full(20, 40.0)], "Volume": 1e6}, index=idx_)
    cfg = {"universe": {"min_market_cap": 10e9, "min_avg_value_20d": 30e6, "min_price": 5}}
    el = eligibility(df, 1.5e8, cfg)      # 150 juta lembar: US$15 miliar lalu US$6 miliar
    assert not el.iloc[:14].any() and el.iloc[14:20].all() and not el.iloc[20:].any()
    # keanggotaan S&P 500: baru masuk indeks di hari ke-17
    member = pd.Series(np.arange(40) >= 16, index=idx_)
    el2 = eligibility(df, 1.5e8, cfg, member)
    assert not el2.iloc[:16].any() and el2.iloc[16:20].all()


def test_sp500_membership():
    from src import sp500
    hist = pd.DataFrame({"code": ["AAA", "AAA", "BBB"],
                         "start": pd.to_datetime(["2020-01-02", "2023-03-01", "2021-06-01"]),
                         "end": pd.to_datetime(["2021-01-04", None, "2024-05-01"])})
    d = pd.to_datetime(["2020-06-01", "2022-01-03", "2023-03-01", "2024-05-01"])
    assert sp500.member_mask(hist, "AAA", d).tolist() == [True, False, True, True]
    assert sp500.member_mask(hist, "BBB", d).tolist() == [False, True, True, False]
    assert sp500.members_since(hist, pd.Timestamp("2024-06-01")) == ["AAA"]
    seed = sp500.current()                          # cadangan bawaan (atau cache) harus terbaca
    assert len(seed) >= 450 and {"code", "name", "sector"} <= set(seed.columns)


def test_symbols_and_positions_parsing():
    from src.data import code_of, ysym
    from src.positions import _num
    assert ysym("BRK.B") == "BRK-B" and code_of("BRK-B") == "BRK.B" and ysym("^GSPC") == "^GSPC"
    assert _num("227.50") == 227.5 and _num("$1,234.56") == 1234.56 and _num("227,5") == 227.5
    assert _num("0.25") == 0.25 and _num("") is None


def test_ranking():
    from src.ranking import rank_value
    c = [("A", 90, 0.03, 0.10), ("B", 65, 0.01, -0.02), ("C", 75, 0.02, 0.20)]
    order = lambda r: [x[0] for x in sorted(c, key=lambda x: rank_value(r, x[1], x[2], x[3], x[0], "2026-10-30"))]  # noqa: E731
    assert order("score") == ["A", "C", "B"] and order("low_score") == ["B", "C", "A"]
    assert order("low_vol") == ["B", "C", "A"] and order("rs") == ["C", "A", "B"]
    assert order("random") == order("random")                         # acak tetapi dapat diulang
    picks = [{"code": k, "ticker": k, "score": s_, "atr_pct": a, "rs_60": r, "sector": k, "entry": 100.0, "sl": 95.0}
             for k, s_, a, r in c]
    out, _ = allocate(picks, {"max_positions": 2, "max_weight": 0.5, "sector_cap": 1.0, "allocation": 0.2,
                              "rank": "low_vol"}, 10_000, 0.01)
    assert sorted(p["code"] for p in out) == ["B", "C"]


def test_monitor():
    from src.monitor import check, streak_prob
    assert abs(streak_prob(3, 3, 0.5) - 0.125) < 1e-9 and streak_prob(5, 1, 0.0) == 0.0
    bt = {"results": {"short": {"n": 300, "avg_ret": 0.01, "win_rate": 0.5, "std_ret": 0.05,
                                "out_sample": {"n": 100, "avg_ret": 0.01, "win_rate": 0.5, "std_ret": 0.05}}}}
    cfg = {"monitor": {"min_trades": 10}}
    few = {"closed_rets": {"short": [["2026-10-01", 0.01]] * 5}}
    assert check(few, bt, cfg)["horizons"]["short"]["level"] == "BELUM CUKUP DATA"
    ok = {"closed_rets": {"short": [["d", r] for r in [0.05, -0.04, 0.03, -0.02, 0.06, -0.03, 0.02, 0.01, -0.01, 0.04] * 2]}}
    assert check(ok, bt, cfg)["horizons"]["short"]["level"] in ("NORMAL", "LEBIH BAIK")
    bad = {"closed_rets": {"short": [["d", -0.04]] * 12}}
    r = check(bad, bt, cfg)
    assert r["horizons"]["short"]["level"] == "BAHAYA" and r["level"] == "BAHAYA"
    # memburuk baru-baru ini: 30 transaksi bagus lalu 20 buruk
    late = {"closed_rets": {"short": [["d", 0.03]] * 30 + [["d", -0.03]] * 20}}
    assert check(late, bt, cfg)["horizons"]["short"]["level"] == "BAHAYA"


def test_config_edit():
    import yaml
    from src.configedit import set_horizon_param
    t = "horizons:\n  short:\n    sl_atr: 2.5     # lama\n    rr: [2.0, 3.0]\n  medium:\n    sl_atr: 3.5\n\nfees:\n  buy: 0.1\n"
    t2 = set_horizon_param(t, "medium", "sl_atr", 4.0, "usulan")
    t2 = set_horizon_param(t2, "short", "rr", [2.5, 4.0])
    t2 = set_horizon_param(t2, "medium", "trend_filter", "sma200")
    y = yaml.safe_load(t2)
    assert y["horizons"]["medium"] == {"sl_atr": 4.0, "trend_filter": "sma200"}
    assert y["horizons"]["short"] == {"sl_atr": 2.5, "rr": [2.5, 4.0]} and y["fees"] == {"buy": 0.1}


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("OK", name)
