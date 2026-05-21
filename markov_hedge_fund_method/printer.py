"""Pretty-print module outputs."""

import numpy as np

REGIMES = ["Bull", "Bear", "Sideways"]


def print_header(ticker: str, start: str, end: str, n_rows: int) -> None:
    print(f"\n{'='*60}")
    print(f"  Markov Regime Model  |  {ticker}")
    print(f"  {start} → {end}  |  {n_rows} trading days")
    print(f"{'='*60}")


def print_transition_matrix(P: np.ndarray) -> None:
    col_w = 10
    print(f"\n{'─'*48}")
    print("  Transition Matrix (row = current, col = next)")
    print(f"{'─'*48}")
    header = "         " + "".join(f"{r:>{col_w}}" for r in REGIMES)
    print(header)
    for i, row_label in enumerate(REGIMES):
        row_str = f"  {row_label:<7}"
        for j, val in enumerate(P[i]):
            cell = f"{val:.4f}"
            if i == j:
                cell = f"[{cell}]"  # highlight persistence diagonal
            row_str += f"{cell:>{col_w}}"
        print(row_str)
    print(f"{'─'*48}")


def print_stationary(pi: np.ndarray) -> None:
    print("\n  Stationary Distribution (long-run regime mix):")
    for regime, p in zip(REGIMES, pi):
        bar = "█" * int(p * 30)
        print(f"    {regime:<9} {p:.4f}  {bar}")


def print_backtest(result: dict) -> None:
    print(f"\n  Walk-Forward Backtest ({result['n_trades']} out-of-sample days)")
    print(f"    Sharpe (annualised) : {result['sharpe']:>8.4f}")
    print(f"    Max Drawdown        : {result['max_drawdown']:>8.2%}")


def print_hmm(hmm_result: dict) -> None:
    if hmm_result is None:
        print("\n  HMM: hmmlearn not installed — skipping.")
        return
    print("\n  Hidden Markov Model  (states sorted by mean return)")
    print(f"    Log-likelihood: {hmm_result['log_likelihood']:.2f}")
    for i, (mu, sigma) in enumerate(zip(hmm_result["means"], hmm_result["std_devs"])):
        label = ["Low", "Mid", "High"][i]
        print(f"    State {i} ({label:>4}):  mean={mu:+.5f}  std={sigma:.5f}")
