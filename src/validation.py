"""Status validasi per horizon: apakah sinyal sudah terbukti lebih baik dari sekadar memegang S&P 500.

Aturan (dihitung ulang setiap backtest, tanpa campur tangan):
  TERVALIDASI        simulasi akun horizon itu di periode out-of-sample (sesudah backtest.split_date)
                     untung DAN Sharpe-nya lebih tinggi dari S&P 500 beli & tahan di periode yang sama
  BELUM TERVALIDASI  selain itu (rugi, atau kalah dari S&P 500)
  BELUM DIUJI        tidak ada data backtest (jangka panjang: butuh fundamental historis)
Status ini ditampilkan di dashboard, Telegram, dan aplikasi laptop agar sinyal yang belum terbukti
tidak dibaca sebagai rekomendasi yang teruji.
"""
from __future__ import annotations

H_LABEL = {"short": "Jangka pendek", "medium": "Jangka menengah", "long": "Jangka panjang"}


def _p(x) -> str:
    return "-" if x is None else f"{100 * x:+.1f}%".replace(".", ",")


def _s(x) -> str:
    return "-" if x is None else f"{x:.2f}".replace(".", ",")


def status(bt: dict | None) -> dict:
    port = (bt or {}).get("portfolio") or {}
    bench = ((port.get("split") or {}).get("bench_out_sample")) or {}
    out = {}
    for h in ("short", "medium", "long"):
        b = (port.get("buckets") or {}).get(h) or {}
        oos = ((b.get("split") or {}).get("out_sample")) or {}
        if h == "long" or not oos or not bench:
            out[h] = {"level": "BELUM DIUJI", "ok": False,
                      "text": ("Belum bisa diuji: butuh data fundamental historis (arsip mulai dikumpulkan harian)."
                               if h == "long" else "Belum ada hasil simulasi akun out-of-sample.")}
            continue
        r, sh, br, bsh = oos.get("total_return"), oos.get("sharpe"), bench.get("total_return"), bench.get("sharpe")
        ok = r is not None and r > 0 and sh is not None and bsh is not None and sh > bsh
        out[h] = {"level": "TERVALIDASI" if ok else "BELUM TERVALIDASI", "ok": bool(ok),
                  "oos_return": r, "oos_sharpe": sh, "bench_return": br, "bench_sharpe": bsh,
                  "since": oos.get("start"),
                  "text": (f"Simulasi akun sejak {oos.get('start', '-')}: {_p(r)} (Sharpe {_s(sh)}) vs S&P 500 "
                           f"beli & tahan {_p(br)} (Sharpe {_s(bsh)}). "
                           + ("Lebih baik dari indeks." if ok else
                              "Belum terbukti lebih baik dari memegang indeks — anggap sinyal ini percobaan "
                              "(paper trading), bukan rekomendasi teruji."))}
    out["any_ok"] = any(v.get("ok") for k, v in out.items() if k in H_LABEL)
    return out
