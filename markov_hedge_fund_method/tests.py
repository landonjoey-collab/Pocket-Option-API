"""Unit tests using synthetic price data (no network required)."""

import numpy as np
import pandas as pd
import unittest

from .model import label_regimes, build_transition_matrix, stationary_distribution, MarkovRegimeModel, REGIMES


def _synthetic_prices(n: int = 500, seed: int = 0) -> pd.Series:
    rng = np.random.default_rng(seed)
    log_rets = rng.normal(0.0003, 0.01, size=n)
    prices = 100.0 * np.exp(np.cumsum(log_rets))
    dates = pd.date_range("2018-01-01", periods=n, freq="B")
    return pd.Series(prices, index=dates, name="synthetic")


class TestLabelRegimes(unittest.TestCase):
    def test_output_contains_only_valid_labels(self):
        prices = _synthetic_prices()
        labels = label_regimes(prices, window=20, threshold=0.02)
        self.assertTrue(set(labels.unique()).issubset(set(REGIMES)))

    def test_length(self):
        prices = _synthetic_prices(300)
        labels = label_regimes(prices, window=20)
        self.assertEqual(len(labels), 300 - 20)


class TestTransitionMatrix(unittest.TestCase):
    def test_rows_sum_to_one(self):
        prices = _synthetic_prices()
        labels = label_regimes(prices)
        P = build_transition_matrix(labels)
        np.testing.assert_allclose(P.sum(axis=1), 1.0, atol=1e-10)

    def test_shape(self):
        prices = _synthetic_prices()
        labels = label_regimes(prices)
        P = build_transition_matrix(labels)
        self.assertEqual(P.shape, (3, 3))


class TestStationaryDistribution(unittest.TestCase):
    def test_sums_to_one(self):
        prices = _synthetic_prices()
        labels = label_regimes(prices)
        P = build_transition_matrix(labels)
        pi = stationary_distribution(P)
        self.assertAlmostEqual(pi.sum(), 1.0, places=6)

    def test_all_non_negative(self):
        prices = _synthetic_prices()
        labels = label_regimes(prices)
        P = build_transition_matrix(labels)
        pi = stationary_distribution(P)
        self.assertTrue(np.all(pi >= 0))


class TestMarkovModel(unittest.TestCase):
    def setUp(self):
        self.prices = _synthetic_prices(600)
        self.model = MarkovRegimeModel(window=20, threshold=0.02)
        self.model.fit(self.prices)

    def test_forecast_sums_to_one(self):
        probs = self.model.forecast(n=1)
        self.assertAlmostEqual(probs.sum(), 1.0, places=6)

    def test_five_step_forecast_sums_to_one(self):
        probs = self.model.forecast(n=5)
        self.assertAlmostEqual(probs.sum(), 1.0, places=6)

    def test_backtest_returns_dict_keys(self):
        result = self.model.walk_forward_backtest(self.prices)
        self.assertIn("sharpe", result)
        self.assertIn("max_drawdown", result)
        self.assertIn("n_trades", result)

    def test_backtest_n_trades_positive(self):
        result = self.model.walk_forward_backtest(self.prices)
        self.assertGreater(result["n_trades"], 0)

    def test_max_drawdown_non_positive(self):
        result = self.model.walk_forward_backtest(self.prices)
        self.assertLessEqual(result["max_drawdown"], 0.0)


if __name__ == "__main__":
    unittest.main()
