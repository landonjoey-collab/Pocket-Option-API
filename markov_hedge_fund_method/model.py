"""Core Markov regime model: labelling, transition matrix, backtest."""

import numpy as np
import pandas as pd


REGIMES = ["Bull", "Bear", "Sideways"]
REGIME_IDX = {r: i for i, r in enumerate(REGIMES)}


def label_regimes(prices: pd.Series, window: int = 20, threshold: float = 0.02) -> pd.Series:
    """Assign Bull / Bear / Sideways based on rolling return over `window` days."""
    rolling_ret = prices.pct_change(window)
    labels = pd.Series("Sideways", index=prices.index, dtype=object)
    labels[rolling_ret > threshold] = "Bull"
    labels[rolling_ret < -threshold] = "Bear"
    return labels.iloc[window:]  # drop the warm-up rows


def build_transition_matrix(labels: pd.Series) -> np.ndarray:
    """MLE 3×3 transition matrix from a sequence of regime labels."""
    counts = np.zeros((3, 3), dtype=float)
    for t in range(len(labels) - 1):
        i = REGIME_IDX[labels.iloc[t]]
        j = REGIME_IDX[labels.iloc[t + 1]]
        counts[i, j] += 1
    # Row-normalise; rows with zero counts stay zero (absorbing by default)
    row_sums = counts.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0] = 1  # avoid divide-by-zero
    return counts / row_sums


def stationary_distribution(P: np.ndarray) -> np.ndarray:
    """Solve π P = π, sum(π) = 1 via left eigenvector of P^T."""
    eigenvalues, eigenvectors = np.linalg.eig(P.T)
    # Eigenvector for eigenvalue closest to 1
    idx = np.argmin(np.abs(eigenvalues - 1.0))
    pi = np.real(eigenvectors[:, idx])
    pi = np.abs(pi)
    return pi / pi.sum()


def n_step_forecast(P: np.ndarray, current_regime: str, n: int = 1) -> np.ndarray:
    """Return the probability distribution over regimes n steps ahead."""
    state = np.zeros(3)
    state[REGIME_IDX[current_regime]] = 1.0
    return state @ np.linalg.matrix_power(P, n)


class MarkovRegimeModel:
    """Observable Markov regime model."""

    def __init__(self, window: int = 20, threshold: float = 0.02):
        self.window = window
        self.threshold = threshold
        self.transition_matrix_: np.ndarray | None = None
        self.stationary_: np.ndarray | None = None
        self.labels_: pd.Series | None = None

    def fit(self, prices: pd.Series) -> "MarkovRegimeModel":
        self.labels_ = label_regimes(prices, self.window, self.threshold)
        self.transition_matrix_ = build_transition_matrix(self.labels_)
        self.stationary_ = stationary_distribution(self.transition_matrix_)
        return self

    def forecast(self, n: int = 1) -> np.ndarray:
        """Probability vector for each regime n steps from the last observed day."""
        if self.labels_ is None:
            raise RuntimeError("Call fit() first.")
        current = self.labels_.iloc[-1]
        return n_step_forecast(self.transition_matrix_, current, n)

    def walk_forward_backtest(self, prices: pd.Series) -> dict:
        """
        Re-estimate the transition matrix at every step using only past data.
        Signal: sign(P(Bull|now) - P(Bear|now)).  Returns Sharpe and max drawdown.
        """
        labels = label_regimes(prices, self.window, self.threshold)
        daily_returns = prices.pct_change().reindex(labels.index)

        min_train = 60  # need at least this many labelled days before trading
        signals = []
        rets = []

        for t in range(min_train, len(labels) - 1):
            past_labels = labels.iloc[:t]
            P = build_transition_matrix(past_labels)
            current = past_labels.iloc[-1]
            probs = n_step_forecast(P, current, 1)
            signal = np.sign(probs[REGIME_IDX["Bull"]] - probs[REGIME_IDX["Bear"]])
            next_ret = daily_returns.iloc[t + 1]
            signals.append(signal)
            rets.append(signal * next_ret)

        rets = np.array(rets, dtype=float)
        # Remove NaN (e.g. from price gaps)
        rets = rets[~np.isnan(rets)]

        sharpe = (rets.mean() / rets.std() * np.sqrt(252)) if rets.std() > 0 else 0.0
        cum = np.cumprod(1 + rets)
        running_max = np.maximum.accumulate(cum)
        drawdowns = (cum - running_max) / running_max
        max_dd = drawdowns.min()

        return {
            "sharpe": round(float(sharpe), 4),
            "max_drawdown": round(float(max_dd), 4),
            "n_trades": len(rets),
        }
