"""Optional Hidden Markov Model layer via hmmlearn (Baum-Welch + Viterbi)."""

import numpy as np
import pandas as pd

try:
    from hmmlearn.hmm import GaussianHMM
    HMM_AVAILABLE = True
except ImportError:
    HMM_AVAILABLE = False


def fit_hmm(prices: pd.Series, n_components: int = 3, random_state: int = 42) -> dict | None:
    """
    Fit a Gaussian HMM on daily log-returns.
    Returns a dict with regime means, covariances, and the Viterbi state sequence,
    or None if hmmlearn is not installed.
    """
    if not HMM_AVAILABLE:
        return None

    log_rets = np.log(prices / prices.shift(1)).dropna().values.reshape(-1, 1)

    model = GaussianHMM(
        n_components=n_components,
        covariance_type="diag",
        n_iter=200,
        random_state=random_state,
    )
    model.fit(log_rets)

    hidden_states = model.predict(log_rets)
    means = model.means_.flatten()

    # Sort states by ascending mean return so state 0 = lowest, 2 = highest
    order = np.argsort(means)
    sorted_means = means[order]
    sorted_covars = model.covars_.flatten()[order]

    return {
        "means": sorted_means,
        "std_devs": np.sqrt(sorted_covars),
        "hidden_states": hidden_states,
        "log_likelihood": model.score(log_rets),
        "transition_matrix": model.transmat_[np.ix_(order, order)],
    }
