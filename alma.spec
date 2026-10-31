# PyInstaller spec — membuat folder "ALMA" berisi "ALMA.exe"
#   pyinstaller --noconfirm alma.spec
from PyInstaller.utils.hooks import collect_all, collect_data_files

datas = [("config.yaml", "."),
         ("data/sp500_seed/sp500.csv", "data/sp500_seed"),
         ("data/sp500_seed/sp500_ticker_start_end.csv", "data/sp500_seed"),
         ("data/sp500_seed/SUMBER.txt", "data/sp500_seed")]
binaries, hiddenimports = [], ["main", "tune", "yaml"]
for pkg in ("curl_cffi", "yfinance"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h
datas += collect_data_files("certifi")

a = Analysis(
    ["app.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["matplotlib", "IPython", "notebook", "pytest", "PyQt5", "PySide6"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ALMA",
    console=False,          # aplikasi berjendela (tanpa layar hitam)
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="ALMA")
