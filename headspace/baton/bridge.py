"""Baton fleet bridge for headspace.

Reads the baton-system hot tier and produces compressed fleet context
for injection into LLM prompts via the headroom proxy.
"""

import os
import re
import json
import time
import subprocess
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

log = logging.getLogger("headspace.baton")

WORKSPACE = Path(os.environ.get("HEADSPACE_WORKSPACE", str(Path.home() / ".openclaw" / "workspace")))
BATON_DIR = Path(os.environ.get("BATON_DIR", str(WORKSPACE / "baton-system")))
HOT_TIER = BATON_DIR / "tiers" / "hot"


def _read_bottle(path: Path) -> Optional[Dict[str, Any]]:
    """Read a single bottle file, extracting metadata."""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        log.warning(f"Could not read {path}: {e}")
        return None
    
    # Extract headers like **Source:** ... **Date:** ...
    meta = {"filename": path.name, "path": str(path)}
    for line in content.splitlines()[:10]:
        m = re.match(r'\*\*([^*]+):\*\*\s*(.+)', line)
        if m:
            meta[m.group(1).strip().lower()] = m.group(2).strip()
    
    # Get a short summary (first non-empty line of body)
    body_lines = [l.strip() for l in content.splitlines() if l.strip() and not l.startswith('#') and not l.startswith('**')]
    meta["summary"] = body_lines[0] if body_lines else ""
    return meta


def sync() -> List[Dict[str, Any]]:
    """Sync: read all hot-tier bottles and return as a list."""
    if not HOT_TIER.exists():
        log.warning(f"Hot tier not found: {HOT_TIER}")
        return []
    
    bottles = []
    for path in sorted(HOT_TIER.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        meta = _read_bottle(path)
        if meta:
            bottles.append(meta)
    return bottles


def fleet_context(max_bottles: int = 5, max_chars_per: int = 200) -> str:
    """Return a compressed fleet context string for prompt injection."""
    bottles = sync()[:max_bottles]
    if not bottles:
        return "<<BATON: no fleet bottles>>"
    
    parts = ["<<BATON:"]
    for b in bottles:
        src = b.get("source", "unknown")[:30]
        summary = b.get("summary", "")[:max_chars_per]
        # ASCII-safe
        summary = summary.encode("ascii", "replace").decode("ascii").replace("?", "")
        parts.append(f"  {src}: {summary}")
    parts.append(">>")
    return "\n".join(parts)


def commit(filename: str, content: str, message: Optional[str] = None) -> Optional[Path]:
    """Create a new bottle in the hot tier and commit it."""
    if not HOT_TIER.exists():
        HOT_TIER.mkdir(parents=True, exist_ok=True)
    
    path = HOT_TIER / filename
    path.write_text(content, encoding="utf-8")
    
    if message is None:
        message = f"headspace: add {filename}"
    
    # Commit and push if git
    try:
        subprocess.run(
            ["git", "add", str(path.relative_to(BATON_DIR))],
            cwd=BATON_DIR, check=True, capture_output=True, timeout=10
        )
        subprocess.run(
            ["git", "commit", "-m", message],
            cwd=BATON_DIR, check=True, capture_output=True, timeout=10
        )
        subprocess.run(
            ["git", "push"],
            cwd=BATON_DIR, check=False, capture_output=True, timeout=30
        )
    except subprocess.CalledProcessError as e:
        log.warning(f"Git commit failed: {e}")
    except FileNotFoundError:
        log.warning("git not found")
    
    return path


def observe(directory: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Watch a directory for incoming bottles (one-shot)."""
    if directory is None:
        directory = BATON_DIR / "i2i-vessel" / "harbor"
    if not directory.exists():
        return []
    bottles = []
    for path in sorted(directory.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        meta = _read_bottle(path)
        if meta:
            bottles.append(meta)
    return bottles


if __name__ == "__main__":
    print(json.dumps(sync(), indent=2)[:2000])
