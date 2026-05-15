"""
Live terminal dashboard powered by Rich.
Runs in its own thread; engine feeds it state updates.
"""
import threading
import time
from datetime import datetime
from typing import TYPE_CHECKING

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

if TYPE_CHECKING:
    from quantum_edge.portfolio import Portfolio
    from quantum_edge.risk import RiskManager


class Dashboard:
    def __init__(self):
        self._lock = threading.Lock()
        self._prices: dict[str, dict] = {}
        self._log_lines: list[str] = []
        self._portfolio: "Portfolio | None" = None
        self._risk: "RiskManager | None" = None
        self._status = "STARTING"
        self._exchange_name = ""
        self._crash_regime = "normal"
        self._crash_severity = 0.0
        self._thread: threading.Thread | None = None
        self._running = threading.Event()

    # ── public API ────────────────────────────────────────────────────────────

    def bind(self, portfolio, risk, exchange_name: str) -> None:
        self._portfolio = portfolio
        self._risk = risk
        self._exchange_name = exchange_name

    def update_price(self, symbol: str, price: float, change_pct: float = 0.0) -> None:
        with self._lock:
            self._prices[symbol] = {"price": price, "change": change_pct, "ts": time.time()}

    def set_status(self, status: str) -> None:
        with self._lock:
            self._status = status

    def set_crash_state(self, regime: str, severity: float) -> None:
        with self._lock:
            self._crash_regime = regime
            self._crash_severity = severity

    def add_log(self, msg: str) -> None:
        with self._lock:
            self._log_lines.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
            if len(self._log_lines) > 60:
                self._log_lines = self._log_lines[-60:]

    def start(self) -> None:
        self._running.set()
        self._thread = threading.Thread(target=self._run, daemon=True, name="dashboard")
        self._thread.start()

    def stop(self) -> None:
        self._running.clear()

    # ── rendering ─────────────────────────────────────────────────────────────

    def _run(self) -> None:
        console = Console()
        with Live(self._render(), console=console, refresh_per_second=2, screen=True) as live:
            while self._running.is_set():
                live.update(self._render())
                time.sleep(1 / 2)

    def _render(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=3),
        )
        layout["main"].split_row(
            Layout(name="left", ratio=2),
            Layout(name="right", ratio=3),
        )
        layout["left"].split_column(
            Layout(name="prices"),
            Layout(name="positions"),
        )
        layout["right"].split_column(
            Layout(name="trades"),
            Layout(name="logs"),
        )

        layout["header"].update(self._header())
        layout["prices"].update(self._price_panel())
        layout["positions"].update(self._position_panel())
        layout["trades"].update(self._trades_panel())
        layout["logs"].update(self._log_panel())
        layout["footer"].update(self._footer())
        return layout

    def _header(self) -> Panel:
        now = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
        balance = self._risk.balance if self._risk else 0
        pnl = self._risk.daily_pnl if self._risk else 0
        pnl_pct = self._risk.daily_pnl_pct if self._risk else 0
        pnl_color = "green" if pnl >= 0 else "red"
        status_color = {"RUNNING": "green", "STARTING": "yellow", "PAUSED": "yellow",
                        "HALTED": "red", "RECONNECTING": "yellow"}.get(self._status, "white")
        text = Text()
        text.append("  QUANTUM EDGE PRO ", style="bold cyan")
        text.append(f"│ {self._exchange_name} │ ", style="dim")
        text.append(f"{self._status} ", style=f"bold {status_color}")
        text.append(f"│ Balance: ${balance:,.2f}  ", style="bold white")
        text.append(f"Daily P&L: ", style="dim")
        text.append(f"${pnl:+.2f} ({pnl_pct:+.1f}%)  ", style=f"bold {pnl_color}")
        crash_labels = {"crash": ("CRASH MODE", "bold red"),
                        "bounce": ("BOUNCE MODE", "bold yellow"),
                        "normal": ("", "dim")}
        cr_label, cr_style = crash_labels.get(self._crash_regime, ("", "dim"))
        if cr_label:
            text.append(f"│ {cr_label} ({self._crash_severity:.0%}) ", style=cr_style)
        text.append(f"│ {now}", style="dim")
        return Panel(text, style="bold blue", box=box.HEAVY)

    def _price_panel(self) -> Panel:
        t = Table(box=box.SIMPLE, show_header=True, expand=True)
        t.add_column("Symbol", style="bold white")
        t.add_column("Price", justify="right")
        t.add_column("24h %", justify="right")
        t.add_column("Age", justify="right", style="dim")

        with self._lock:
            items = list(self._prices.items())

        for sym, d in sorted(items):
            chg = d["change"]
            chg_style = "green" if chg >= 0 else "red"
            age = int(time.time() - d["ts"])
            t.add_row(
                sym,
                f"{d['price']:,.6f}",
                Text(f"{chg:+.2f}%", style=chg_style),
                f"{age}s",
            )
        return Panel(t, title="[bold]Market Prices", border_style="blue")

    def _position_panel(self) -> Panel:
        t = Table(box=box.SIMPLE, show_header=True, expand=True)
        t.add_column("Symbol", style="bold white")
        t.add_column("Side")
        t.add_column("Entry", justify="right")
        t.add_column("P&L", justify="right")
        t.add_column("Bars", justify="right", style="dim")

        if self._portfolio:
            for pos in self._portfolio.all_positions():
                side_style = "green" if pos.side == "long" else "red"
                pnl_style = "green" if pos.unrealized_pnl >= 0 else "red"
                t.add_row(
                    pos.symbol,
                    Text(pos.side.upper(), style=side_style),
                    f"{pos.entry_price:,.6f}",
                    Text(f"${pos.unrealized_pnl:+.2f}", style=pnl_style),
                    str(pos.candles_held),
                )
        return Panel(t, title="[bold]Open Positions", border_style="magenta")

    def _trades_panel(self) -> Panel:
        t = Table(box=box.SIMPLE, show_header=True, expand=True)
        t.add_column("Time")
        t.add_column("Symbol", style="bold white")
        t.add_column("Side")
        t.add_column("Entry", justify="right")
        t.add_column("Exit", justify="right")
        t.add_column("P&L", justify="right")
        t.add_column("Reason", style="dim")

        if self._portfolio:
            for tr in reversed(self._portfolio.recent_trades(15)):
                side_style = "green" if tr["side"] == "long" else "red"
                pnl_style = "green" if tr["pnl"] >= 0 else "red"
                ts = tr["timestamp"][:19].replace("T", " ")
                t.add_row(
                    ts,
                    tr["symbol"],
                    Text(tr["side"].upper(), style=side_style),
                    f"{tr['entry']:.4f}",
                    f"{tr['exit']:.4f}",
                    Text(f"${tr['pnl']:+.2f}", style=pnl_style),
                    tr["reason"],
                )
        return Panel(t, title="[bold]Recent Trades", border_style="cyan")

    def _log_panel(self) -> Panel:
        with self._lock:
            lines = list(self._log_lines[-12:])
        text = "\n".join(lines) if lines else "(waiting for events…)"
        return Panel(text, title="[bold]Activity Log", border_style="dim")

    def _footer(self) -> Panel:
        risk = self._risk
        streak = risk.consecutive_losses if risk else 0
        streak_style = "red bold" if streak >= 3 else "yellow" if streak >= 2 else "green"
        pos_count = self._portfolio.count() if self._portfolio else 0
        text = Text()
        text.append(f"  Positions: {pos_count}/{config_val('MAX_OPEN_POSITIONS')}  │  ", style="dim")
        text.append(f"Loss streak: ", style="dim")
        text.append(f"{streak}  ", style=streak_style)
        text.append("│  Press Ctrl+C to stop", style="dim")
        return Panel(text, style="dim", box=box.SIMPLE)


def config_val(name: str):
    from quantum_edge import config
    return getattr(config, name, "?")
