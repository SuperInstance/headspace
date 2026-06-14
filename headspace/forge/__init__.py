"""Forge context — cold-start bootstrap snapshot for headspace agents.

Reads the forgemaster CONTEXT.md and forging-log.md to build a
compact state vector that agents can use for cold-start bootstrap.
"""

import os
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger("headspace.forge")

WORKSPACE = Path(os.environ.get("HEADSPACE_WORKSPACE", str(Path.home() / ".openclaw" / "workspace")))
FORGE_DIR = WORKSPACE / "state" / ".forge"


def forge_snapshot() -> Optional[str]:
    """Read forgemaster state and return a compact compressed string."""
    ctx_file = FORGE_DIR / "CONTEXT.md"
    if not ctx_file.exists():
        return None
    
    try:
        content = ctx_file.read_text(encoding="utf-8", errors="replace")
        # Extract active systems + integration points
        lines = content.splitlines()
        active = []
        collecting = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("## Active"):
                collecting = True
                continue
            if stripped.startswith("## Integration"):
                collecting = False
                continue
            if collecting and stripped.startswith("- **"):
                # Format: "- **GC**: ..."
                name = stripped.split("**")[1] if "**" in stripped else "?"
                active.append(name)
        
        # Check forging log for latest entries
        log_file = FORGE_DIR / "forging-log.md"
        last_entry = ""
        if log_file.exists():
            log_content = log_file.read_text(encoding="utf-8", errors="replace")
            # Find last date heading
            for line in reversed(log_content.splitlines()):
                if line.startswith("## "):
                    last_entry = line.replace("## ", "").strip()
                    break
        
        # Build compact state
        systems = ",".join(active) if active else "GC,PID,Swarm,Baton,Headroom"
        result = f"<<FORGE: {systems} :: last: {last_entry}>>"
        
        return result.encode("ascii", errors="replace").decode("ascii").replace("?", "")
    
    except Exception as e:
        log.warning("Forge snapshot error: %s", e)
        return None


if __name__ == "__main__":
    snap = forge_snapshot()
    print(snap or "no forge data")
