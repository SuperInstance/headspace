"""Forgemaster protocol - orchestrate the headspace install.

The forge-apply pattern: check that all required subsystems are present
and report health, mirroring the Oracle2 scripts/forge-apply.sh but as
a Python module so headspace can self-validate anywhere.
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List

WORKSPACE = Path(os.environ.get("HEADSPACE_WORKSPACE", str(Path.home() / ".openclaw" / "workspace")))


def check_components() -> Dict[str, bool]:
    """Check that all required components are present."""
    checks = {}
    
    # Headroom CLI
    checks["headroom"] = shutil.which("headroom") is not None
    
    # Headroom extension
    try:
        import importlib.util
        # First try the standard import
        spec = importlib.util.find_spec("headroom_superinstance")
        if spec is not None:
            checks["headroom_superinstance"] = True
        else:
            # Try the workspace location (subpackage or flat)
            ext_subpkg = WORKSPACE / "headroom-superinstance" / "headroom_superinstance" / "__init__.py"
            ext_flat = WORKSPACE / "headroom-superinstance" / "extension.py"
            checks["headroom_superinstance"] = ext_subpkg.exists() or ext_flat.exists()
    except (ImportError, ModuleNotFoundError):
        checks["headroom_superinstance"] = False
    
    # Swarm advisor
    checks["ternary_gc_advisor"] = (WORKSPACE / "scripts" / "ternary-gc-advisor.py").exists()
    
    # Baton system
    checks["baton_system"] = (WORKSPACE / "baton-system").exists()
    
    # GC ledger
    checks["gc_ledger"] = (WORKSPACE / "data" / "gc-ledger" / "ledger.jsonl").exists()
    
    return checks


def report() -> str:
    """Generate a human-readable health report."""
    checks = check_components()
    lines = ["Headspace forge check:"]
    for name, ok in checks.items():
        mark = "OK" if ok else "MISSING"
        lines.append(f"  [{mark}] {name}")
    return "\n".join(lines)


def is_healthy() -> bool:
    """Return True if all critical components are present."""
    checks = check_components()
    return checks.get("headroom", False) and checks.get("ternary_gc_advisor", False)


if __name__ == "__main__":
    print(report())
    import sys
    sys.exit(0 if is_healthy() else 1)
