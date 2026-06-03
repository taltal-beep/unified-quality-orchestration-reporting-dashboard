"""Tests for :mod:`testo_core.engine.log_buffer`."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from testo_core.engine.log_buffer import (
    DEFAULT_RING_BYTES,
    LogBuffer,
    drain_stream_into_buffer,
    merged_env,
)


def test_log_buffer_tees_to_disk(tmp_path: Path) -> None:
    log_path = tmp_path / "run.log"
    with LogBuffer(log_path=log_path, ring_bytes=1024) as buf:
        buf.feed(b"line1\n")
        buf.feed(b"line2\n")
    assert log_path.read_bytes() == b"line1\nline2\n"


def test_log_buffer_ring_evicts_oldest(tmp_path: Path) -> None:
    log_path = tmp_path / "run.log"
    capacity = 32
    with LogBuffer(log_path=log_path, ring_bytes=capacity) as buf:
        # Each chunk is 20 bytes; third chunk should evict the first from the ring.
        buf.feed(b"a" * 20)
        buf.feed(b"b" * 20)
        buf.feed(b"c" * 20)
        tail = buf.tail()
    assert len(tail.encode()) <= capacity + 20
    assert "c" in tail
    assert log_path.stat().st_size == 60


def test_log_buffer_on_chunk_called(tmp_path: Path) -> None:
    log_path = tmp_path / "run.log"
    seen: list[bytes] = []

    def on_chunk(chunk: bytes) -> None:
        seen.append(chunk)

    with LogBuffer(log_path=log_path, on_chunk=on_chunk) as buf:
        buf.feed(b"x")
    assert seen == [b"x"]


def test_log_buffer_on_chunk_exception_swallowed(tmp_path: Path) -> None:
    log_path = tmp_path / "run.log"

    def boom(_chunk: bytes) -> None:
        raise RuntimeError("renderer blew up")

    with LogBuffer(log_path=log_path, on_chunk=boom) as buf:
        buf.feed(b"ok")
    assert log_path.read_bytes() == b"ok"


def test_log_buffer_tail_max_lines_and_bytes(tmp_path: Path) -> None:
    log_path = tmp_path / "run.log"
    with LogBuffer(log_path=log_path, ring_bytes=DEFAULT_RING_BYTES) as buf:
        for i in range(10):
            buf.feed(f"line{i}\n".encode())
        text = buf.tail(max_lines=3, max_bytes=20)
    lines = text.splitlines()
    assert len(lines) <= 3


def test_drain_stream_into_buffer_reads_eof(tmp_path: Path) -> None:
    log_path = tmp_path / "run.log"
    stream = io.BytesIO(b"abc\ndef\n")
    with LogBuffer(log_path=log_path) as buf:
        drain_stream_into_buffer(stream, buf)
    assert buf.tail() == "abc\ndef\n"


def test_merged_env_overlays_extra() -> None:
    parent = {"A": "1", "B": "2"}
    out = merged_env(parent, [("B", "override"), ("C", "3")])
    assert out == {"A": "1", "B": "override", "C": "3"}
