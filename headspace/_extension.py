"""Headspace ASGI middleware for the headroom proxy.

Compresses SuperInstance fleet data (GC ledger, swarm state, baton)
into compact context injected into every LLM request.

This module is a re-export/shared import for the headspace package.
The canonical standalone version lives at headroom-superinstance/extension.py
"""

from __future__ import annotations

import json
import os
import logging
import re
from pathlib import Path
from typing import Any, Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

log = logging.getLogger("headspace.extension")

WORKSPACE = Path(os.environ.get("WORKSPACE", str(Path.home() / ".openclaw" / "workspace")))
GC_LEDGER = WORKSPACE / "data" / "gc-ledger" / "ledger.jsonl"
PID_STATE = WORKSPACE / "data" / "gc-ledger" / "pid-state.json"
BATON_HOT = WORKSPACE / "baton-system" / "tiers" / "hot"
FORGE_STATE = WORKSPACE / "state" / ".forge"
GC_SAMPLE_SIZE = 100

_VERSION = "0.2.0"


def _ascii(s: str) -> str:
    return s.encode("ascii", errors="replace").decode("ascii")


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _compress_gc_ledger(max_entries: int = GC_SAMPLE_SIZE) -> str:
    """Lossless schema-compression of GC ledger."""
    if not GC_LEDGER.exists():
        return "<<GC ledger: no data>>"
    try:
        raw = GC_LEDGER.read_text(encoding="utf-8", errors="replace")
        lines = [l.strip() for l in raw.splitlines() if l.strip() and l.startswith("{")]
        if not lines:
            return "<<GC ledger: empty>>"
        n_total = len(lines)
        sample = lines[-max_entries:]
        entries = []
        for line in sample:
            try:
                e = json.loads(line)
                entries.append(e)
            except json.JSONDecodeError:
                continue
        if not entries:
            return "<<GC ledger: no valid entries>>"
        n_valid = len(entries)
        disk_pct = entries[-1].get("disk_pct", 0)
        total_freed = sum(e.get("freed_kb", 0) or 0 for e in entries)
        actions = {}
        for e in entries:
            a = e.get("action", "?")
            actions[a] = actions.get(a, 0) + 1
        agg = entries[-1].get("aggression", "?")
        action_str = " ".join(f"{k}:{v}" for k, v in sorted(actions.items()))
        return (f"<<GC ledger:{n_total} sampled:{n_valid} disk:{disk_pct}%"
                f" freed:{total_freed}kb agg:{agg} [{action_str}]>>")
    except Exception as exc:
        log.warning("GC compression error: %s", exc)
        return "<<GC ledger: error>>"


def _compress_swarm_state() -> str:
    """Compress swarm advisor PID state."""
    state = _load_json(PID_STATE)
    if not state:
        return "<<SWARM: no state>>"
    kp = state.get("kp", 0)
    ki = state.get("ki", 0)
    kd = state.get("kd", 0)
    return f"<<SWARM kp:{kp} ki:{ki} kd:{kd}>>"


def _inject_baton_context(max_bottles: int = 5) -> str:
    """Read baton hot-tier and produce summary."""
    if not BATON_HOT.exists():
        return "<<BATON: no fleet bottles>>"
    bottles = sorted(BATON_HOT.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    parts = []
    for bottle in bottles[:max_bottles]:
        content = bottle.read_text(encoding="utf-8", errors="replace")
        source = "?"
        for line in content.splitlines()[:10]:
            m = re.search(r"\*\*Source:\*\*\s*(.+)", line)
            if m:
                source = m.group(1).strip()[:30]
        summary = " ".join(
            l.strip() for l in content.splitlines()
            if l.strip() and not l.startswith("#") and not l.startswith("**")
        )[:100]
        parts.append(f"  {source}: {summary}")
    if not parts:
        return "<<BATON: empty>>"
    return "<<BATON:\n" + "\n".join(parts) + "\n>>"


def _forge_context() -> str:
    """Read forgemaster CONTEXT.md snapshot."""
    ctx_file = FORGE_STATE / "CONTEXT.md"
    if not ctx_file.exists():
        return ""
    content = ctx_file.read_text(encoding="utf-8", errors="replace")[:300]
    return f"<<FORGE: {content[:200].replace(chr(10), ' ')}>>"


def compress_for_prompt() -> str:
    """Combined compressed context for prompt injection."""
    parts = []
    gc = _compress_gc_ledger()
    if gc:
        parts.append(_ascii(gc))
    swarm = _compress_swarm_state()
    if swarm:
        parts.append(_ascii(swarm))
    baton = _inject_baton_context()
    if baton:
        parts.append(_ascii(baton))
    forge = _forge_context()
    if forge:
        parts.append(_ascii(forge))
    return "\n".join(parts) if parts else ""


class SuperInstanceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        try:
            # GC ledger
            gc = _compress_gc_ledger()
            if gc:
                response.headers["x-headspace-gc"] = _ascii(gc)
            # Swarm state
            swarm = _compress_swarm_state()
            if swarm:
                response.headers["x-headspace-swarm"] = _ascii(swarm)
            # Baton context
            baton = _inject_baton_context()
            if baton:
                response.headers["x-headspace-baton"] = _ascii(baton)
            # Version
            response.headers["x-headspace"] = _VERSION
        except Exception as exc:
            log.warning("Middleware header injection failed: %s", exc)
        return response


__all__ = [
    "SuperInstanceMiddleware",
    "compress_for_prompt",
    "_compress_gc_ledger",
    "_compress_swarm_state",
    "_inject_baton_context",
    "_forge_context",
]
