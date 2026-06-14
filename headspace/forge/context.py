"""Forge context - snapshot of the headspace state for cold-start bootstrap."""

import json
import os
import time
from pathlib import Path
from typing import Optional, Dict, Any

WORKSPACE = Path(os.environ.get("HEADSPACE_WORKSPACE", str(Path.home() / ".openclaw" / "workspace")))


def forge_snapshot() -> Dict[str, Any]:
    """Capture the current headspace state as a single dict.

    Returns: dict with keys like:
      - ts: timestamp
      - proxy: status of headroom proxy
      - swarm: status of swarm advisory
      - extension: status of headroom_superinstance
      - baton: number of bottles
      - ledger: number of entries
    """
    snapshot = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "app": "headspace",
        "version": "0.2.0",
    }

    # Headroom proxy
    try:
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:8788/livez", timeout=2) as r:
            data = json.loads(r.read())
            snapshot["proxy"] = "running" if data.get("alive") else "down"
    except Exception:
        snapshot["proxy"] = "down"

    # Swarm advisory
    try:
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:18000/healthz", timeout=2) as r:
            data = json.loads(r.read())
            snapshot["swarm"] = "running" if data.get("status") == "ok" else "down"
    except Exception:
        snapshot["swarm"] = "down"

    # Extension
    try:
        from headroom_superinstance import __version__
        snapshot["extension"] = f"v{__version__}"
    except ImportError:
        snapshot["extension"] = "missing"

    # Baton bottles
    try:
        from headspace.baton import sync
        snapshot["baton_bottles"] = len(sync())
    except Exception:
        snapshot["baton_bottles"] = 0

    # GC ledger
    ledger_path = WORKSPACE / "data" / "gc-ledger" / "ledger.jsonl"
    if ledger_path.exists():
        try:
            with open(ledger_path) as f:
                snapshot["ledger_entries"] = sum(1 for _ in f)
        except Exception:
            snapshot["ledger_entries"] = 0
    else:
        snapshot["ledger_entries"] = 0

    return snapshot


if __name__ == "__main__":
    print(json.dumps(forge_snapshot(), indent=2))
