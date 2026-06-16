"""Core financial engine for the ValueQuant Robo-Advisor.

This module keeps portfolio construction, risk profiling, rebalancing and
brokerage simulation independent from Streamlit. It can be reused from a REST
API, scheduled jobs, tests or the Telegram alert bot.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Mapping, Sequence
from uuid import uuid4

import numpy as np
import pandas as pd
from scipy.optimize import minimize


OrderSide = Literal["buy", "sell"]


class FinancialEngineError(Exception):
    """Base exception for financial engine failures."""


class InvalidReturnDataError(FinancialEngineError):
    """Raised when historical return data cannot be optimized safely."""


class OptimizationError(FinancialEngineError):
    """Raised when the optimizer cannot converge to a valid solution."""


class RiskProfileError(FinancialEngineError):
    """Raised when the risk questionnaire or score is invalid."""


class BrokerAPIError(FinancialEngineError):
    """Raised when a simulated brokerage operation fails."""


class InsufficientCashError(BrokerAPIError):
    """Raised when a buy order exceeds available cash."""


class OrderValidationError(BrokerAPIError):
    """Raised when a market order request is malformed."""


@dataclass(frozen=True)
class OptimizationResult:
    """Result returned by Markowitz optimization routines."""

    weights: pd.Series
    expected_return: float
    volatility: float
    sharpe_ratio: float
    objective: str
    success: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serializes the optimization result into a JSON-friendly dict.

        Returns:
            Dictionary with weights, expected return, volatility and Sharpe
            ratio using native Python numeric types.
        """
        return {
            "weights": {
                str(asset): round(float(weight), 6)
                for asset, weight in self.weights.items()
            },
            "expected_return": round(float(self.expected_return), 6),
            "volatility": round(float(self.volatility), 6),
            "sharpe_ratio": round(float(self.sharpe_ratio), 6),
            "objective": self.objective,
            "success": self.success,
        }


@dataclass(frozen=True)
class RebalanceTrade:
    """Trade recommendation produced by drift-based rebalancing."""

    symbol: str
    side: OrderSide
    current_weight: float
    target_weight: float
    drift: float
    notional: float

    def to_dict(self) -> dict[str, Any]:
        """Serializes the recommendation into a JSON-friendly dict.

        Returns:
            Dictionary with side, drift and order notional.
        """
        return {
            "symbol": self.symbol,
            "side": self.side,
            "current_weight": round(float(self.current_weight), 6),
            "target_weight": round(float(self.target_weight), 6),
            "drift": round(float(self.drift), 6),
            "notional": round(float(self.notional), 2),
        }


@dataclass(frozen=True)
class BrokerOrder:
    """Alpaca-style simulated market order."""

    id: str
    symbol: str
    side: OrderSide
    quantity: float
    notional: float
    price: float
    order_type: str
    time_in_force: str
    status: str
    submitted_at: datetime
    filled_at: datetime

    def to_dict(self) -> dict[str, Any]:
        """Serializes the simulated order into a JSON-friendly dict.

        Returns:
            Order payload similar to an Alpaca API response.
        """
        return {
            "id": self.id,
            "symbol": self.symbol,
            "side": self.side,
            "qty": round(float(self.quantity), 6),
            "notional": round(float(self.notional), 2),
            "filled_avg_price": round(float(self.price), 4),
            "type": self.order_type,
            "time_in_force": self.time_in_force,
            "status": self.status,
            "submitted_at": self.submitted_at.isoformat(),
            "filled_at": self.filled_at.isoformat(),
        }


@dataclass
class BrokerPosition:
    """Current simulated position inside the broker sandbox."""

    symbol: str
    quantity: float
    average_price: float

    def market_value(self, last_price: float) -> float:
        """Calculates current market value for the position.

        Args:
            last_price: Latest executable market price.

        Returns:
            Current position market value.
        """
        return float(self.quantity * last_price)


@dataclass(frozen=True)
class RiskProfileResult:
    """Structured result returned by the risk profiler."""

    score_total: float
    score_1_to_10: int
    risk_category: str
    recommended_asset_allocation: dict[str, float]
    dimension_scores: dict[str, float]
    warnings: list[str] = field(default_factory=list)
    behavioral_notes: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        """Serializes the risk profile into the requested JSON object.

        Returns:
            JSON-ready object with score, category, allocation and warnings.
        """
        return {
            "score_total": round(float(self.score_total), 2),
            "score_1_to_10": self.score_1_to_10,
            "risk_category": self.risk_category,
            "recommended_asset_allocation": {
                asset: round(float(weight), 4)
                for asset, weight in self.recommended_asset_allocation.items()
            },
            "dimension_scores": {
                dimension: round(float(score), 2)
                for dimension, score in self.dimension_scores.items()
            },
            "warnings": list(self.warnings),
            "behavioral_notes": list(self.behavioral_notes),
        }


RISK_PROFILE_QUESTIONS: dict[str, dict[str, Any]] = {
    "time_horizon": {
        "dimension": "time_horizon",
        "weight": 0.25,
        "question": "Cuando preves retirar mas del 25% de esta inversion?",
        "behavioral_finance_rationale": (
            "Time horizon measures objective risk capacity: long horizons reduce "
            "sequence-of-returns risk and make temporary drawdowns easier to absorb."
        ),
        "options": {
            "lt_2y": {"label": "Menos de 2 anos", "score": 0.0},
            "2_5y": {"label": "Entre 2 y 5 anos", "score": 4.0},
            "5_10y": {"label": "Entre 5 y 10 anos", "score": 7.0},
            "gt_10y": {"label": "Mas de 10 anos", "score": 10.0},
        },
    },
    "risk_tolerance": {
        "dimension": "risk_tolerance",
        "weight": 0.40,
        "question": "Si una cartera de 10,000 cae a 8,000 en un mes, que haces?",
        "behavioral_finance_rationale": (
            "Risk tolerance receives the largest weight because loss aversion "
            "and panic selling usually damage outcomes more than small allocation "
            "differences."
        ),
        "options": {
            "sell_all": {"label": "Vendo todo para detener la perdida", "score": 0.0},
            "sell_some": {"label": "Vendo una parte de la cartera", "score": 3.0},
            "hold": {"label": "Mantengo y espero la recuperacion", "score": 7.0},
            "buy_more": {"label": "Invierto mas aprovechando precios bajos", "score": 10.0},
        },
    },
    "financial_knowledge": {
        "dimension": "financial_knowledge",
        "weight": 0.15,
        "question": "En que productos has invertido dinero real?",
        "behavioral_finance_rationale": (
            "Knowledge is useful but intentionally weighted below behavior and "
            "capacity because experienced investors can still suffer from "
            "overconfidence and confirmation bias."
        ),
        "options": {
            "cash_deposits": {"label": "Efectivo, depositos o cuentas remuneradas", "score": 1.0},
            "funds_etfs": {"label": "Fondos de inversion o ETFs", "score": 5.0},
            "stocks_bonds": {"label": "Acciones o bonos individuales", "score": 7.0},
            "complex_assets": {"label": "Opciones, futuros, cripto o mercados privados", "score": 10.0},
        },
    },
    "wealth_situation": {
        "dimension": "wealth_situation",
        "weight": 0.20,
        "question": "Como de solido es tu colchon de emergencia y capacidad de ahorro?",
        "behavioral_finance_rationale": (
            "Solvency protects the investor from forced selling. A cash buffer "
            "reduces myopic loss aversion because market stress does not become "
            "an immediate liquidity crisis."
        ),
        "options": {
            "fragile": {"label": "Sin colchon o ingresos inestables", "score": 0.0},
            "thin": {"label": "1-3 meses de gastos cubiertos", "score": 3.0},
            "solid": {"label": "3-6 meses cubiertos y ahorro regular", "score": 7.0},
            "strong": {"label": "Mas de 6 meses cubiertos y ahorro alto", "score": 10.0},
        },
    },
}


class PortfolioOptimizer:
    """Markowitz optimizer for ETF historical return series."""

    def __init__(
        self,
        historical_returns: pd.DataFrame,
        risk_free_rate: float = 0.02,
        periods_per_year: int = 252,
        long_only: bool = True,
    ) -> None:
        """Initializes the optimizer with historical ETF returns.

        Args:
            historical_returns: DataFrame of periodic returns where columns are
                ETF tickers and rows are observations.
            risk_free_rate: Annualized risk-free rate used in Sharpe ratio.
            periods_per_year: Number of return observations per year.
            long_only: Whether weights are constrained to the [0, 1] interval.

        Raises:
            InvalidReturnDataError: If the return matrix is empty, non-numeric
                or has fewer than two assets.
        """
        self.returns = self._validate_returns(historical_returns)
        self.risk_free_rate = float(risk_free_rate)
        self.periods_per_year = int(periods_per_year)
        self.long_only = bool(long_only)
        self.assets = list(self.returns.columns)

    @classmethod
    def from_price_history(
        cls,
        prices: pd.DataFrame,
        risk_free_rate: float = 0.02,
        periods_per_year: int = 252,
        long_only: bool = True,
    ) -> "PortfolioOptimizer":
        """Builds an optimizer from ETF price history.

        Args:
            prices: DataFrame of historical prices with ETF tickers as columns.
            risk_free_rate: Annualized risk-free rate used in Sharpe ratio.
            periods_per_year: Number of price observations per year.
            long_only: Whether weights are constrained to the [0, 1] interval.

        Returns:
            PortfolioOptimizer initialized with percentage returns.

        Raises:
            InvalidReturnDataError: If prices cannot produce enough returns.
        """
        if not isinstance(prices, pd.DataFrame):
            raise InvalidReturnDataError("prices must be a pandas DataFrame.")
        clean_prices = prices.apply(pd.to_numeric, errors="coerce")
        clean_prices = clean_prices.dropna(axis=1, how="all").dropna(how="any")
        returns = clean_prices.pct_change(fill_method=None).dropna(how="any")
        return cls(
            returns,
            risk_free_rate=risk_free_rate,
            periods_per_year=periods_per_year,
            long_only=long_only,
        )

    def annualized_expected_returns(self) -> pd.Series:
        """Calculates annualized expected returns.

        Returns:
            Series indexed by asset ticker with annualized arithmetic returns.
        """
        return self.returns.mean() * self.periods_per_year

    def annualized_covariance(self) -> pd.DataFrame:
        """Calculates the annualized covariance matrix.

        Returns:
            DataFrame covariance matrix annualized by the configured frequency.
        """
        return self.returns.cov() * self.periods_per_year

    def portfolio_return(self, weights: Sequence[float] | np.ndarray) -> float:
        """Calculates expected annual return for a weight vector.

        Args:
            weights: Portfolio weights ordered like ``self.assets``.

        Returns:
            Expected annualized portfolio return.
        """
        weights_array = self._coerce_weights(weights)
        return float(np.dot(weights_array, self.annualized_expected_returns().to_numpy()))

    def portfolio_volatility(self, weights: Sequence[float] | np.ndarray) -> float:
        """Calculates annualized portfolio volatility.

        Args:
            weights: Portfolio weights ordered like ``self.assets``.

        Returns:
            Annualized standard deviation.
        """
        weights_array = self._coerce_weights(weights)
        covariance = self.annualized_covariance().to_numpy()
        variance = float(weights_array.T @ covariance @ weights_array)
        return float(np.sqrt(max(variance, 0.0)))

    def maximize_sharpe(self) -> OptimizationResult:
        """Finds the portfolio that maximizes the Sharpe ratio.

        Returns:
            OptimizationResult containing optimal weights and metrics.

        Raises:
            OptimizationError: If SciPy cannot find a valid SLSQP solution.
        """
        result = self._solve(
            objective=self._negative_sharpe_ratio,
            constraints=[self._fully_invested_constraint()],
            objective_name="max_sharpe",
        )
        return self._result_from_weights(result.x, objective="max_sharpe")

    def minimize_volatility(self) -> OptimizationResult:
        """Finds the global minimum variance portfolio.

        Returns:
            OptimizationResult containing optimal weights and metrics.

        Raises:
            OptimizationError: If SciPy cannot find a valid SLSQP solution.
        """
        result = self._solve(
            objective=lambda weights: self.portfolio_volatility(weights),
            constraints=[self._fully_invested_constraint()],
            objective_name="min_volatility",
        )
        return self._result_from_weights(result.x, objective="min_volatility")

    def optimize_for_target_return(self, target_return: float) -> OptimizationResult:
        """Minimizes volatility for a required annual return.

        Args:
            target_return: Annualized target return, expressed as a decimal.

        Returns:
            OptimizationResult for the target-return efficient portfolio.

        Raises:
            OptimizationError: If the requested target is infeasible.
        """
        result = self._solve(
            objective=lambda weights: self.portfolio_volatility(weights),
            constraints=[
                self._fully_invested_constraint(),
                {
                    "type": "eq",
                    "fun": lambda weights: self.portfolio_return(weights)
                    - float(target_return),
                },
            ],
            objective_name=f"target_return_{target_return:.4f}",
        )
        return self._result_from_weights(result.x, objective="target_return")

    def efficient_frontier(self, points: int = 50) -> pd.DataFrame:
        """Calculates a Markowitz efficient frontier with SciPy SLSQP.

        Args:
            points: Number of target-return portfolios to calculate.

        Returns:
            DataFrame with expected return, volatility, Sharpe ratio and weights
            for each efficient portfolio.

        Raises:
            OptimizationError: If no frontier point can be solved.
        """
        if points < 2:
            raise OptimizationError("efficient_frontier requires at least 2 points.")

        expected_returns = self.annualized_expected_returns()
        target_grid = np.linspace(
            float(expected_returns.min()),
            float(expected_returns.max()),
            int(points),
        )
        rows: list[dict[str, Any]] = []

        for target_return in target_grid:
            try:
                result = self.optimize_for_target_return(float(target_return))
            except OptimizationError:
                continue
            rows.append(
                {
                    "target_return": float(target_return),
                    "expected_return": result.expected_return,
                    "volatility": result.volatility,
                    "sharpe_ratio": result.sharpe_ratio,
                    "weights": {
                        asset: float(weight)
                        for asset, weight in result.weights.items()
                    },
                }
            )

        if not rows:
            raise OptimizationError("No efficient frontier point could be solved.")
        return pd.DataFrame(rows)

    def _validate_returns(self, returns: pd.DataFrame) -> pd.DataFrame:
        if not isinstance(returns, pd.DataFrame):
            raise InvalidReturnDataError("historical_returns must be a pandas DataFrame.")

        clean_returns = returns.copy()
        clean_returns.columns = [str(column).upper() for column in clean_returns.columns]
        clean_returns = clean_returns.apply(pd.to_numeric, errors="coerce")
        clean_returns = clean_returns.dropna(axis=1, how="all").dropna(how="any")

        if clean_returns.shape[1] < 2:
            raise InvalidReturnDataError("At least two assets are required.")
        if clean_returns.shape[0] < 30:
            raise InvalidReturnDataError("At least 30 return observations are required.")
        if not np.isfinite(clean_returns.to_numpy()).all():
            raise InvalidReturnDataError("Return matrix contains non-finite values.")

        zero_variance_assets = clean_returns.columns[clean_returns.std() == 0].tolist()
        if zero_variance_assets:
            raise InvalidReturnDataError(
                f"Assets with zero variance cannot be optimized: {zero_variance_assets}"
            )

        return clean_returns

    def _bounds(self) -> list[tuple[float, float]]:
        if self.long_only:
            return [(0.0, 1.0) for _ in self.assets]
        return [(-1.0, 1.0) for _ in self.assets]

    def _coerce_weights(self, weights: Sequence[float] | np.ndarray) -> np.ndarray:
        weights_array = np.asarray(weights, dtype=float)
        if weights_array.shape != (len(self.assets),):
            raise OptimizationError(
                f"Expected {len(self.assets)} weights, got {weights_array.shape}."
            )
        return weights_array

    def _fully_invested_constraint(self) -> dict[str, Any]:
        return {"type": "eq", "fun": lambda weights: np.sum(weights) - 1.0}

    def _initial_weights(self) -> np.ndarray:
        return np.repeat(1.0 / len(self.assets), len(self.assets))

    def _negative_sharpe_ratio(self, weights: Sequence[float] | np.ndarray) -> float:
        volatility = self.portfolio_volatility(weights)
        if volatility <= 0:
            return 1e9
        return -((self.portfolio_return(weights) - self.risk_free_rate) / volatility)

    def _solve(
        self,
        objective: Any,
        constraints: list[dict[str, Any]],
        objective_name: str,
    ) -> Any:
        result = minimize(
            objective,
            self._initial_weights(),
            method="SLSQP",
            bounds=self._bounds(),
            constraints=constraints,
            options={"maxiter": 1000, "ftol": 1e-10, "disp": False},
        )
        if not result.success:
            raise OptimizationError(f"{objective_name} failed: {result.message}")
        return result

    def _result_from_weights(
        self,
        weights: Sequence[float] | np.ndarray,
        objective: str,
    ) -> OptimizationResult:
        weights_array = np.asarray(weights, dtype=float)
        weights_series = pd.Series(weights_array, index=self.assets)
        weights_series = weights_series.mask(weights_series.abs() < 1e-10, 0.0)
        if self.long_only:
            weights_series = weights_series.clip(lower=0.0)
        if np.isclose(weights_series.sum(), 0.0):
            raise OptimizationError("Optimized weights sum to zero.")
        weights_series = weights_series / weights_series.sum()
        expected_return = self.portfolio_return(weights_series.to_numpy())
        volatility = self.portfolio_volatility(weights_series.to_numpy())
        sharpe_ratio = (
            (expected_return - self.risk_free_rate) / volatility
            if volatility > 0
            else np.nan
        )
        return OptimizationResult(
            weights=weights_series,
            expected_return=float(expected_return),
            volatility=float(volatility),
            sharpe_ratio=float(sharpe_ratio),
            objective=objective,
        )


def calculate_drift_rebalancing(
    current_weights: Mapping[str, float],
    target_weights: Mapping[str, float],
    portfolio_value: float,
    tolerance_bands: Mapping[str, float] | float = 0.05,
    min_trade_value: float = 25.0,
) -> list[RebalanceTrade]:
    """Calculates buy/sell orders when allocation drift exceeds tolerance bands.

    Args:
        current_weights: Current portfolio weights by symbol.
        target_weights: Target model weights by symbol.
        portfolio_value: Current total portfolio value in base currency.
        tolerance_bands: Either one global tolerance or per-symbol tolerances.
        min_trade_value: Minimum order notional to avoid noisy tiny trades.

    Returns:
        List of RebalanceTrade recommendations sorted by absolute notional.

    Raises:
        RiskProfileError: If weights, tolerance bands or portfolio value are
            invalid.
    """
    if portfolio_value <= 0:
        raise RiskProfileError("portfolio_value must be positive.")
    if min_trade_value < 0:
        raise RiskProfileError("min_trade_value cannot be negative.")

    current = _normalize_weights(current_weights, "current_weights")
    target = _normalize_weights(target_weights, "target_weights")
    symbols = sorted(set(current) | set(target))
    trades: list[RebalanceTrade] = []

    for symbol in symbols:
        current_weight = current.get(symbol, 0.0)
        target_weight = target.get(symbol, 0.0)
        band = _tolerance_for_symbol(symbol, tolerance_bands)
        drift = current_weight - target_weight

        if abs(drift) <= band:
            continue

        target_notional = target_weight * portfolio_value
        current_notional = current_weight * portfolio_value
        trade_notional = target_notional - current_notional

        if abs(trade_notional) < min_trade_value:
            continue

        trades.append(
            RebalanceTrade(
                symbol=symbol,
                side="buy" if trade_notional > 0 else "sell",
                current_weight=current_weight,
                target_weight=target_weight,
                drift=drift,
                notional=abs(float(trade_notional)),
            )
        )

    return sorted(trades, key=lambda trade: abs(trade.notional), reverse=True)


class AlpacaBrokerSimulator:
    """Small Alpaca-style broker simulator for market-order integration tests."""

    def __init__(self, initial_cash: float = 100_000.0) -> None:
        """Initializes the broker sandbox.

        Args:
            initial_cash: Starting cash balance.

        Raises:
            BrokerAPIError: If initial cash is negative.
        """
        if initial_cash < 0:
            raise BrokerAPIError("initial_cash cannot be negative.")
        self.cash = float(initial_cash)
        self.positions: dict[str, BrokerPosition] = {}
        self.last_prices: dict[str, float] = {}
        self.orders: list[BrokerOrder] = []

    def update_market_price(self, symbol: str, price: float) -> None:
        """Updates the executable market price used by the simulator.

        Args:
            symbol: Security ticker.
            price: Latest market price.

        Raises:
            BrokerAPIError: If price is not strictly positive.
        """
        normalized_symbol = symbol.upper().strip()
        if not normalized_symbol:
            raise BrokerAPIError("symbol is required.")
        if price <= 0:
            raise BrokerAPIError("Market price must be positive.")
        self.last_prices[normalized_symbol] = float(price)

    def submit_market_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float | None = None,
        notional: float | None = None,
        time_in_force: str = "day",
    ) -> BrokerOrder:
        """Submits a simulated market order and updates cash and positions.

        Args:
            symbol: Security ticker.
            side: Order side, either ``buy`` or ``sell``.
            quantity: Share quantity. Mutually exclusive with notional.
            notional: Cash amount to trade. Mutually exclusive with quantity.
            time_in_force: Alpaca-style time in force field.

        Returns:
            Filled BrokerOrder payload.

        Raises:
            OrderValidationError: If order fields are malformed.
            InsufficientCashError: If a buy order exceeds cash.
            BrokerAPIError: If a sell order exceeds current holdings.
        """
        normalized_symbol = symbol.upper().strip()
        normalized_side = side.lower()
        if normalized_side not in {"buy", "sell"}:
            raise OrderValidationError("side must be 'buy' or 'sell'.")
        if not normalized_symbol:
            raise OrderValidationError("symbol is required.")
        if (quantity is None and notional is None) or (
            quantity is not None and notional is not None
        ):
            raise OrderValidationError("Provide exactly one of quantity or notional.")

        price = self._last_price(normalized_symbol)
        trade_quantity = (
            float(quantity) if quantity is not None else float(notional) / price
        )
        if trade_quantity <= 0:
            raise OrderValidationError("quantity/notional must be positive.")

        trade_notional = trade_quantity * price
        if normalized_side == "buy":
            self._execute_buy(normalized_symbol, trade_quantity, price, trade_notional)
        else:
            self._execute_sell(normalized_symbol, trade_quantity, trade_notional)

        now = datetime.now(timezone.utc)
        order = BrokerOrder(
            id=str(uuid4()),
            symbol=normalized_symbol,
            side=normalized_side,  # type: ignore[arg-type]
            quantity=trade_quantity,
            notional=trade_notional,
            price=price,
            order_type="market",
            time_in_force=time_in_force,
            status="filled",
            submitted_at=now,
            filled_at=now,
        )
        self.orders.append(order)
        return order

    def portfolio_value(self) -> float:
        """Calculates current cash plus market value of all positions.

        Returns:
            Total simulated account equity.

        Raises:
            BrokerAPIError: If a position has no updated market price.
        """
        positions_value = sum(
            position.market_value(self._last_price(symbol))
            for symbol, position in self.positions.items()
        )
        return float(self.cash + positions_value)

    def positions_frame(self) -> pd.DataFrame:
        """Returns current simulated positions as a pandas DataFrame.

        Returns:
            DataFrame with symbol, quantity, market price, market value and PnL.
        """
        rows: list[dict[str, Any]] = []
        for symbol, position in self.positions.items():
            last_price = self._last_price(symbol)
            market_value = position.market_value(last_price)
            cost_basis = position.quantity * position.average_price
            rows.append(
                {
                    "symbol": symbol,
                    "quantity": position.quantity,
                    "average_price": position.average_price,
                    "last_price": last_price,
                    "market_value": market_value,
                    "unrealized_pnl": market_value - cost_basis,
                    "unrealized_pnl_pct": (
                        (market_value - cost_basis) / cost_basis if cost_basis else 0.0
                    ),
                }
            )
        return pd.DataFrame(
            rows,
            columns=[
                "symbol",
                "quantity",
                "average_price",
                "last_price",
                "market_value",
                "unrealized_pnl",
                "unrealized_pnl_pct",
            ],
        )

    def _last_price(self, symbol: str) -> float:
        try:
            return self.last_prices[symbol]
        except KeyError as exc:
            raise BrokerAPIError(f"No market price available for {symbol}.") from exc

    def _execute_buy(
        self,
        symbol: str,
        quantity: float,
        price: float,
        notional: float,
    ) -> None:
        if notional > self.cash + 1e-9:
            raise InsufficientCashError(
                f"Insufficient cash: required {notional:.2f}, available {self.cash:.2f}."
            )
        existing = self.positions.get(symbol)
        if existing is None:
            self.positions[symbol] = BrokerPosition(symbol, quantity, price)
        else:
            new_quantity = existing.quantity + quantity
            existing_cost = existing.quantity * existing.average_price
            new_average = (existing_cost + notional) / new_quantity
            self.positions[symbol] = BrokerPosition(symbol, new_quantity, new_average)
        self.cash -= notional

    def _execute_sell(self, symbol: str, quantity: float, notional: float) -> None:
        existing = self.positions.get(symbol)
        if existing is None or quantity > existing.quantity + 1e-9:
            held = 0.0 if existing is None else existing.quantity
            raise BrokerAPIError(
                f"Cannot sell {quantity:.6f} {symbol}; current quantity is {held:.6f}."
            )
        remaining_quantity = existing.quantity - quantity
        if remaining_quantity <= 1e-9:
            self.positions.pop(symbol, None)
        else:
            self.positions[symbol] = BrokerPosition(
                symbol,
                remaining_quantity,
                existing.average_price,
            )
        self.cash += notional


class RiskProfileManager:
    """Maps a 1-10 risk score to professional asset-class allocations."""

    _ALLOCATIONS_BY_SCORE: tuple[tuple[range, str, dict[str, float]], ...] = (
        (
            range(1, 3),
            "Conservador",
            {"Stocks": 0.20, "Bonds": 0.75, "Commodities": 0.03, "Real Estate": 0.02},
        ),
        (
            range(3, 7),
            "Moderado",
            {"Stocks": 0.50, "Bonds": 0.40, "Commodities": 0.05, "Real Estate": 0.05},
        ),
        (
            range(7, 9),
            "Crecimiento",
            {"Stocks": 0.75, "Bonds": 0.15, "Commodities": 0.05, "Real Estate": 0.05},
        ),
        (
            range(9, 11),
            "Agresivo",
            {"Stocks": 0.90, "Bonds": 0.02, "Commodities": 0.03, "Real Estate": 0.05},
        ),
    )

    def allocation_for_score(self, score: int) -> dict[str, float]:
        """Returns target asset-class weights for a 1-10 risk score.

        Args:
            score: Integer risk score from 1 to 10.

        Returns:
            Asset allocation dictionary whose weights sum to 1.

        Raises:
            RiskProfileError: If score is outside the supported range.
        """
        if not isinstance(score, int) or score < 1 or score > 10:
            raise RiskProfileError("Risk score must be an integer from 1 to 10.")
        for score_range, _, allocation in self._ALLOCATIONS_BY_SCORE:
            if score in score_range:
                return dict(allocation)
        raise RiskProfileError(f"No allocation configured for score {score}.")

    def category_for_score(self, score: int) -> str:
        """Returns the risk category for a 1-10 score.

        Args:
            score: Integer risk score from 1 to 10.

        Returns:
            Risk category name.

        Raises:
            RiskProfileError: If score is outside the supported range.
        """
        if not isinstance(score, int) or score < 1 or score > 10:
            raise RiskProfileError("Risk score must be an integer from 1 to 10.")
        for score_range, category, _ in self._ALLOCATIONS_BY_SCORE:
            if score in score_range:
                return category
        raise RiskProfileError(f"No category configured for score {score}.")

    def allocation_for_category(self, category: str) -> dict[str, float]:
        """Returns target asset-class weights for a named category.

        Args:
            category: Risk category name.

        Returns:
            Asset allocation dictionary whose weights sum to 1.

        Raises:
            RiskProfileError: If category is unknown.
        """
        normalized_category = category.strip().lower()
        for _, configured_category, allocation in self._ALLOCATIONS_BY_SCORE:
            if configured_category.lower() == normalized_category:
                return dict(allocation)
        raise RiskProfileError(f"Unknown risk category: {category}.")


class RiskProfiler:
    """Behavioral-finance risk profiler for Robo-Advisor onboarding.

    The scoring model separates objective capacity from subjective willingness:
    time horizon and wealth situation represent the client's ability to take
    risk, while the drawdown reaction captures loss aversion. Tolerance receives
    40% of the score because behavioral finance research consistently shows
    that the investor's reaction during market stress is often the binding
    constraint. Financial knowledge receives 15% because it helps, but excessive
    weight would reward overconfidence rather than actual staying power.
    """

    def __init__(
        self,
        questions: Mapping[str, Mapping[str, Any]] | None = None,
        profile_manager: RiskProfileManager | None = None,
    ) -> None:
        """Initializes the risk profiler.

        Args:
            questions: Optional custom question dictionary.
            profile_manager: Optional allocation manager.
        """
        self.questions = dict(questions or RISK_PROFILE_QUESTIONS)
        self.profile_manager = profile_manager or RiskProfileManager()
        self._validate_question_weights()

    def calculate_score(self, answers: Mapping[str, str]) -> dict[str, Any]:
        """Calculates the risk score and recommended allocation.

        Args:
            answers: Mapping from question id to selected option id. Example:
                ``{"time_horizon": "gt_10y", "risk_tolerance": "hold"}``.

        Returns:
            JSON-ready object containing ``score_total``, ``risk_category`` and
            ``recommended_asset_allocation``.

        Raises:
            RiskProfileError: If an answer is missing or not configured.
        """
        dimension_scores: dict[str, list[float]] = {}

        for question_id, question in self.questions.items():
            selected_option = answers.get(question_id)
            options = question["options"]
            if selected_option not in options:
                raise RiskProfileError(
                    f"Invalid answer for {question_id}: {selected_option!r}."
                )
            dimension = str(question["dimension"])
            option_score = float(options[selected_option]["score"])
            dimension_scores.setdefault(dimension, []).append(option_score)

        averaged_dimensions = {
            dimension: float(np.mean(scores))
            for dimension, scores in dimension_scores.items()
        }
        weighted_score_0_to_10 = sum(
            averaged_dimensions[str(question["dimension"])] * float(question["weight"])
            for question in self.questions.values()
        )
        score_total = float(np.clip(weighted_score_0_to_10 * 10.0, 0.0, 100.0))
        score_1_to_10 = int(np.clip(np.floor(score_total / 10.0) + 1, 1, 10))
        category = self._category_from_total_score(score_total)
        allocation = self.profile_manager.allocation_for_category(category)
        warnings = self._validate_inconsistencies(answers, averaged_dimensions)
        notes = self._behavioral_notes()

        return RiskProfileResult(
            score_total=score_total,
            score_1_to_10=score_1_to_10,
            risk_category=category,
            recommended_asset_allocation=allocation,
            dimension_scores=averaged_dimensions,
            warnings=warnings,
            behavioral_notes=notes,
        ).to_json()

    def _validate_question_weights(self) -> None:
        total_weight = sum(float(question["weight"]) for question in self.questions.values())
        if not np.isclose(total_weight, 1.0, atol=1e-6):
            raise RiskProfileError(
                f"Risk question weights must sum to 1.0, got {total_weight:.4f}."
            )

    def _category_from_total_score(self, score_total: float) -> str:
        if score_total < 20:
            return "Conservador"
        if score_total < 60:
            return "Moderado"
        if score_total < 85:
            return "Crecimiento"
        return "Agresivo"

    def _validate_inconsistencies(
        self,
        answers: Mapping[str, str],
        dimension_scores: Mapping[str, float],
    ) -> list[str]:
        warnings: list[str] = []
        horizon_is_short = answers.get("time_horizon") == "lt_2y"
        tolerance_is_high = dimension_scores.get("risk_tolerance", 0.0) >= 8.0
        wealth_is_fragile = dimension_scores.get("wealth_situation", 10.0) <= 3.0

        if horizon_is_short and tolerance_is_high:
            warnings.append(
                "Review suggested: the investor selected a horizon below 2 years "
                "while also choosing high risk tolerance. Capacity and willingness "
                "are inconsistent."
            )
        if wealth_is_fragile and tolerance_is_high:
            warnings.append(
                "Review suggested: high risk appetite conflicts with a fragile "
                "liquidity buffer. Forced selling risk is elevated."
            )
        if (
            answers.get("risk_tolerance") == "sell_all"
            and answers.get("financial_knowledge") == "complex_assets"
        ):
            warnings.append(
                "Review suggested: complex-product experience is paired with a "
                "panic-selling response. This may indicate overconfidence under "
                "normal conditions and fragility under stress."
            )
        return warnings

    def _behavioral_notes(self) -> list[str]:
        return [
            "Risk tolerance is weighted at 40% to control for loss aversion and panic-selling risk.",
            "Time horizon and wealth buffer represent objective risk capacity, not personal preference.",
            "Financial knowledge is capped at 15% to avoid over-rewarding overconfidence.",
        ]


def _normalize_weights(weights: Mapping[str, float], field_name: str) -> dict[str, float]:
    if not weights:
        raise RiskProfileError(f"{field_name} cannot be empty.")

    normalized: dict[str, float] = {}
    for symbol, weight in weights.items():
        clean_symbol = str(symbol).upper().strip()
        clean_weight = float(weight)
        if not clean_symbol:
            raise RiskProfileError(f"{field_name} contains an empty symbol.")
        if clean_weight < 0:
            raise RiskProfileError(f"{field_name} contains a negative weight: {symbol}.")
        normalized[clean_symbol] = clean_weight

    total = sum(normalized.values())
    if total <= 0:
        raise RiskProfileError(f"{field_name} weights must sum to a positive value.")
    return {symbol: weight / total for symbol, weight in normalized.items()}


def _tolerance_for_symbol(
    symbol: str,
    tolerance_bands: Mapping[str, float] | float,
) -> float:
    if isinstance(tolerance_bands, Mapping):
        normalized_bands = {
            str(ticker).upper().strip(): float(tolerance)
            for ticker, tolerance in tolerance_bands.items()
        }
        tolerance = float(normalized_bands.get(symbol, 0.05))
    else:
        tolerance = float(tolerance_bands)
    if tolerance < 0:
        raise RiskProfileError("Tolerance bands cannot be negative.")
    return tolerance
