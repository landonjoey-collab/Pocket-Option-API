"""Entry point: python -m markov_hedge_fund_method.run --ticker SPY"""

import argparse
import sys

import yfinance as yf

from .model import MarkovRegimeModel
from .hmm_layer import fit_hmm
from .printer import (
    print_header,
    print_transition_matrix,
    print_stationary,
    print_backtest,
    print_hmm,
)


def fetch_prices(ticker: str, years: int, csv_path: str | None = None) -> "pd.Series":
    import pandas as pd

    if csv_path:
        df = pd.read_csv(csv_path, parse_dates=True, index_col=0)
        col = next((c for c in df.columns if c.lower() in ("close", "adj close", "price")), df.columns[0])
        return df[col].dropna().rename(ticker)

    end = pd.Timestamp.today()
    start = end - pd.DateOffset(years=years)
    df = yf.download(ticker, start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"),
                     auto_adjust=True, progress=False)
    if df.empty:
        print(f"ERROR: No data returned for '{ticker}'. Check the ticker symbol.", file=sys.stderr)
        sys.exit(1)
    close = df["Close"]
    if isinstance(close, type(df)):  # multi-column edge case
        close = close.iloc[:, 0]
    close = close.squeeze()
    return close.dropna()


def run(ticker: str, years: int = 10, window: int = 20, threshold: float = 0.02,
        use_hmm: bool = True, csv_path: str | None = None) -> None:
    prices = fetch_prices(ticker, years, csv_path=csv_path)

    print_header(
        ticker=ticker.upper(),
        start=str(prices.index[0].date()),
        end=str(prices.index[-1].date()),
        n_rows=len(prices),
    )

    model = MarkovRegimeModel(window=window, threshold=threshold)
    model.fit(prices)

    print_transition_matrix(model.transition_matrix_)
    print_stationary(model.stationary_)

    backtest_result = model.walk_forward_backtest(prices)
    print_backtest(backtest_result)

    # Current regime and 1-step forecast
    current = model.labels_.iloc[-1]
    probs_1 = model.forecast(n=1)
    probs_5 = model.forecast(n=5)
    print(f"\n  Current regime  : {current}")
    print(f"  1-day forecast  : Bull={probs_1[0]:.3f}  Bear={probs_1[1]:.3f}  Sideways={probs_1[2]:.3f}")
    print(f"  5-day forecast  : Bull={probs_5[0]:.3f}  Bear={probs_5[1]:.3f}  Sideways={probs_5[2]:.3f}")

    if use_hmm:
        hmm_result = fit_hmm(prices)
        print_hmm(hmm_result)

    print(f"\n{'='*60}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Observable Markov regime model for any Yahoo Finance ticker."
    )
    parser.add_argument("--ticker", required=True, help="Ticker symbol (e.g. SPY, BTC-USD)")
    parser.add_argument("--years", type=int, default=10, help="Years of history to fetch (default: 10)")
    parser.add_argument("--window", type=int, default=20, help="Rolling return window in days (default: 20)")
    parser.add_argument("--threshold", type=float, default=0.02,
                        help="±threshold to classify Bull/Bear vs Sideways (default: 0.02)")
    parser.add_argument("--no-hmm", dest="use_hmm", action="store_false",
                        help="Skip the optional HMM layer")
    parser.add_argument("--csv", dest="csv_path", default=None,
                        help="Path to a CSV file with a date index and a Close column "
                             "(bypasses yfinance; useful offline)")
    args = parser.parse_args()
    run(ticker=args.ticker, years=args.years, window=args.window,
        threshold=args.threshold, use_hmm=args.use_hmm, csv_path=args.csv_path)


if __name__ == "__main__":
    main()
