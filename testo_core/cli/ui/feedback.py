"""Small helpers for consistent Rich completion lines in the CLI."""

from __future__ import annotations

from rich.console import Console


def print_ok(console: Console, message: str) -> None:
    console.print(f"[ok]{message}[/]")


def print_fail(console: Console, message: str) -> None:
    console.print(f"[fail]{message}[/]")


def print_warn(console: Console, message: str) -> None:
    console.print(f"[warn]{message}[/]")
