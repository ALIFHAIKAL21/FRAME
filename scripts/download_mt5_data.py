

import argparse
import sys
import pathlib
from datetime import datetime, timedelta

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def download_mt5_data(symbol, years, output_path):
    try:
        import MetaTrader5 as mt5
    except ImportError:
        print("[ERROR] Package MetaTrader5 tidak terinstal.")
        print("  Jalankan: pip install MetaTrader5")
        sys.exit(1)

    import pandas as pd

    print("[MT5] Menginisialisasi koneksi...")
    if not mt5.initialize():
        print("[ERROR] MT5 initialize() gagal: {}".format(mt5.last_error()))
        print("  Pastikan MetaTrader 5 Terminal sedang berjalan dan login.")
        mt5.shutdown()
        sys.exit(1)

    info = mt5.terminal_info()
    if info is not None:
        print("[MT5] Terminal: {}".format(info.name))
        print("[MT5] Broker: {}".format(info.company))
        print("[MT5] Connected: {}".format(info.connected))

    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        print("[ERROR] Symbol '{}' tidak ditemukan di broker ini.".format(symbol))
        print("  Coba nama alternatif: XAUUSD, XAUUSDm, GOLD, XAU/USD")
        all_symbols = mt5.symbols_get()
        if all_symbols:
            gold_symbols = [s.name for s in all_symbols
                           if "XAU" in s.name.upper() or "GOLD" in s.name.upper()]
            if gold_symbols:
                print("  Simbol Gold yang tersedia: {}".format(gold_symbols))
        mt5.shutdown()
        sys.exit(1)

    if not symbol_info.visible:
        if not mt5.symbol_select(symbol, True):
            print("[ERROR] Gagal mengaktifkan symbol {}".format(symbol))
            mt5.shutdown()
            sys.exit(1)

    date_to = datetime.utcnow()
    date_from = date_to - timedelta(days=years * 365)

    print("[MT5] Mengunduh {} M30 dari {} sampai {}...".format(symbol, date_from.date(), date_to.date()))

    rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M30, date_from, date_to)

    if rates is None or len(rates) == 0:
        print("[ERROR] Tidak ada data yang diunduh: {}".format(mt5.last_error()))
        mt5.shutdown()
        sys.exit(1)

    df = pd.DataFrame(rates)
    print("[MT5] Data diterima: {:,} bar".format(len(df)))

    df["timestamp_utc"] = pd.to_datetime(df["time"], unit="s", utc=True)

    df_out = pd.DataFrame({
        "timestamp_utc": df["timestamp_utc"],
        "open": df["open"],
        "high": df["high"],
        "low": df["low"],
        "close": df["close"],
        "volume": df["tick_volume"],
        "spread": df["spread"] / 10.0,
    })

    df_out = df_out.sort_values("timestamp_utc").reset_index(drop=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df_out.to_csv(output_path, index=False)
    print("[MT5] Data disimpan ke: {}".format(output_path))
    print("[MT5] Total bars: {:,}".format(len(df_out)))
    print("[MT5] Rentang: {} -> {}".format(df_out["timestamp_utc"].iloc[0], df_out["timestamp_utc"].iloc[-1]))

    print("\n--- Quick Stats ---")
    print("  Price range: {:.2f} - {:.2f}".format(df_out["low"].min(), df_out["high"].max()))
    print("  Mean spread: {:.2f} pips".format(df_out["spread"].mean()))
    print("  Days covered: {}".format((df_out["timestamp_utc"].max() - df_out["timestamp_utc"].min()).days))

    mt5.shutdown()
    print("[MT5] Koneksi ditutup. Selesai.")


def main():
    parser = argparse.ArgumentParser(
        description="Download XAU/USD M30 historical data from MetaTrader 5"
    )
    parser.add_argument("--symbol", type=str, default="XAUUSD",
                        help="Symbol name in MT5 (default: XAUUSD)")
    parser.add_argument("--years", type=int, default=5,
                        help="Number of years of historical data (default: 5)")
    parser.add_argument("--output", type=str, default=None,
                        help="Output CSV file path")

    args = parser.parse_args()

    if args.output:
        output_path = pathlib.Path(args.output)
    else:
        output_path = PROJECT_ROOT / "data" / "raw" / "xauusd_m30_raw.csv"

    download_mt5_data(args.symbol, args.years, output_path)


if __name__ == "__main__":
    main()
