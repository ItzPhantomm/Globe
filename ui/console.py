"""
Globe Selfbot — Rich Console UI
Minimal, clean terminal interface powered by Rich.
"""

from __future__ import annotations

from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme
from rich import box

# ── Custom theme ──────────────────────────────────────────────────────────────
GLOBE_THEME = Theme(
    {
        "globe.brand": "bold bright_cyan",
        "globe.ok": "bold bright_green",
        "globe.warn": "bold bright_yellow",
        "globe.err": "bold bright_red",
        "globe.muted": "dim white",
        "globe.cmd": "bold white",
        "globe.accent": "bold magenta",
        "globe.ts": "dim cyan",
    }
)

console = Console(theme=GLOBE_THEME, highlight=False)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def banner() -> None:
    """Print the Globe startup banner."""
    art = Text(
        "\n"
        "   ██████╗ ██╗      ██████╗ ██████╗ ███████╗\n"
        "  ██╔════╝ ██║     ██╔═══██╗██╔══██╗██╔════╝\n"
        "  ██║  ███╗██║     ██║   ██║██████╔╝█████╗  \n"
        "  ██║   ██║██║     ██║   ██║██╔══██╗██╔══╝  \n"
        "  ╚██████╔╝███████╗╚██████╔╝██████╔╝███████╗\n"
        "   ╚═════╝ ╚══════╝ ╚═════╝ ╚═════╝ ╚══════╝\n",
        style="globe.brand",
        justify="center",
    )
    sub = Text("  all-in-one discord selfbot  ·  prefix: g.", style="globe.muted", justify="center")
    console.print(art)
    console.print(sub)
    console.print()


def print_startup_table(token_preview: str, prefix: str, owner_id: int, module_count: int) -> None:
    table = Table(box=box.ROUNDED, border_style="bright_cyan", show_header=False, padding=(0, 1))
    table.add_column("key", style="globe.muted", width=16)
    table.add_column("value", style="bold white")
    table.add_row("token", token_preview)
    table.add_row("prefix", prefix)
    table.add_row("owner", str(owner_id) if owner_id else "not set")
    table.add_row("modules", str(module_count))
    console.print(Panel(table, title="[globe.brand]Globe[/]", border_style="bright_cyan"))


def log_info(msg: str) -> None:
    console.print(f"[globe.ts]{_ts()}[/] [globe.ok]INFO[/]  {msg}")


def log_warn(msg: str) -> None:
    console.print(f"[globe.ts]{_ts()}[/] [globe.warn]WARN[/]  {msg}")


def log_err(msg: str) -> None:
    console.print(f"[globe.ts]{_ts()}[/] [globe.err] ERR[/]  {msg}")


def log_cmd(ctx_name: str, cmd: str, args: str = "") -> None:
    args_part = f" [globe.muted]{args}[/]" if args else ""
    console.print(
        f"[globe.ts]{_ts()}[/] [globe.accent] CMD[/]  "
        f"[globe.cmd]{ctx_name}[/] → [globe.brand]{cmd}[/]{args_part}"
    )


def log_event(event: str, detail: str = "") -> None:
    detail_part = f" [globe.muted]· {detail}[/]" if detail else ""
    console.print(f"[globe.ts]{_ts()}[/] [bright_blue]  EV[/]  {event}{detail_part}")
