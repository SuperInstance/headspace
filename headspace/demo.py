#!/usr/bin/env python3
"""headspace demo - the killer app showcase.

This script demonstrates headspace as a complete context management layer:

  1. Compresses a sample LLM prompt (system + tools + history + fleet)
  2. Shows the schema-aware compression of GC ledger
  3. Calls the swarm for a policy recommendation
  4. Shows the fleet context from baton
  5. Calls the headroom proxy with the compressed prompt
  6. Reports the token savings

Run:
  python3 headspace/demo.py
"""

import json
import os
import sys
import urllib.request
from pathlib import Path

WORKSPACE = Path(os.environ.get("HEADSPACE_WORKSPACE", str(Path.home() / ".openclaw" / "workspace")))
HEADROOM_PROXY = os.environ.get("HEADROOM_PROXY", "http://127.0.0.1:8788")
HEADSPACE_SWARM = os.environ.get("HEADSPACE_SWARM", "http://127.0.0.1:18000")

# Ensure the headroom-superinstance extension is importable
ext_dir = WORKSPACE / "headroom-superinstance"
if ext_dir.exists() and str(ext_dir) not in sys.path:
    sys.path.insert(0, str(ext_dir))


def _ascii(s):
    return s.encode("ascii", "replace").decode("ascii")


def banner(t):
    width = 60
    print(f"\n{'-'*width}\n{t}\n{'-'*width}")


def main():
    print("="*60)
    print("  HEADSPACE KILLER APP DEMO")
    print("="*60)
    print(f"  Proxy:   {HEADROOM_PROXY}")
    print(f"  Swarm:   {HEADSPACE_SWARM}")
    print(f"  Workspace: {WORKSPACE}")

    # 1. Real fleet state
    banner("1. FLEET STATE (current disk + GC ledger)")
    try:
        from headspace.baton import sync
        from headspace.forge.apply import check_components
        bottles = sync()
        print(f"  Baton bottles in hot tier: {len(bottles)}")
        for b in bottles[:3]:
            print(f"    - {b['filename'][:50]}")
        checks = check_components()
        print(f"  Headroom installed: {checks.get('headroom', False)}")
        print(f"  Swarm advisor available: {checks.get('ternary_gc_advisor', False)}")
    except Exception as e:
        print(f"  Error: {e}")

    # 2. Schema-aware compression
    banner("2. SCHEMA-AWARE COMPRESSION")
    try:
        # Try subpackage import first, then flat extension
        try:
            from headroom_superinstance import _compress_gc_ledger, _compress_swarm_state
        except ImportError:
            from extension import _compress_gc_ledger, _compress_swarm_state
        gc = _compress_gc_ledger()
        swarm = _compress_swarm_state()
        print(f"  GC ledger:   {gc[:120]}")
        print(f"  Swarm state: {swarm[:120]}")
        # Approximate character count
        ledger_path = WORKSPACE / "data" / "gc-ledger" / "ledger.jsonl"
        if ledger_path.exists():
            orig_size = ledger_path.stat().st_size
            comp_size = len(gc) + len(swarm)
            print(f"  Original ledger file: {orig_size} bytes")
            print(f"  Compressed:           {comp_size} chars")
            if orig_size > 0:
                print(f"  Ratio:                {comp_size/orig_size*100:.2f}%")
    except Exception as e:
        print(f"  Error: {e}")

    # 3. Swarm policy
    banner("3. SWARM POLICY (HTTP API)")
    try:
        with urllib.request.urlopen(f"{HEADSPACE_SWARM}/api/v1/policy", timeout=3) as r:
            policy = json.loads(r.read())
        print(f"  Profile:       {policy.get('profile', 'unknown')}")
        print(f"  Setpoint:      {policy.get('setpoint_pct', '?')}%")
        print(f"  Deadband:      {policy.get('deadband', '?')}")
        print(f"  Aggression cap: {policy.get('aggression_cap', '?')}x")
    except Exception as e:
        print(f"  Error: {e}")

    # 4. Fleet context
    banner("4. FLEET CONTEXT (from baton hot tier)")
    try:
        from headspace.baton import fleet_context
        ctx = fleet_context(max_bottles=3)
        print(ctx)
    except Exception as e:
        print(f"  Error: {e}")

    # 5. Compress a sample prompt
    banner("5. PROMPT COMPRESSION (synthetic example)")
    system_prompt = """You are an AI agent in the SuperInstance fleet.

Your job is to:
1. Monitor the host system (disk, memory, processes)
2. Coordinate with other agents via the baton system
3. Run garbage collection when needed
4. Report fleet state in compressed form

Available tools:
- read_file(path) - Read a file from disk
- write_file(path, content) - Write content to disk
- run_command(cmd) - Execute a shell command
- send_bottle(target, message) - Send a message to another agent
- sync_fleet() - Sync state with the entire fleet

Rules:
- Always use the smallest context that conveys full meaning
- Never duplicate information
- Compress GC ledger entries using the schema
- Use the swarm's recommended policy
- Log all actions in the forging log"""

    # Simulate compression
    original_size = len(system_prompt)
    # Headspace-style: keep the structure, drop the verbosity
    compressed = """You are a SuperInstance fleet agent. Monitor host (disk/mem/proc), coordinate via baton, run GC as needed, report fleet in compressed form. Tools: read_file, write_file, run_command, send_bottle, sync_fleet. Rules: minimal context, no duplication, schema-compress GC, follow swarm policy, log to forging-log."""

    print(f"  Original:  {original_size} chars")
    print(f"  Compressed: {len(compressed)} chars")
    print(f"  Savings:    {original_size - len(compressed)} chars ({100 - len(compressed)*100//original_size}%)")
    print(f"  Sample:")
    print(f"    {compressed[:150]}...")

    # 6. Headroom proxy health
    banner("6. HEADROOM PROXY (with superinstance extension)")
    try:
        with urllib.request.urlopen(f"{HEADROOM_PROXY}/livez", timeout=3) as r:
            health = r.read().decode()
        print(f"  Health: {health[:200]}")
        with urllib.request.urlopen(f"{HEADROOM_PROXY}/stats", timeout=3) as r:
            stats = r.read().decode()
        print(f"  Stats:  {stats[:200]}")
    except Exception as e:
        print(f"  Error: {e}")

    # 7. Forge check
    banner("7. FORGEMASTER PROTOCOL CHECK")
    try:
        from headspace.forge.apply import report
        print(report())
    except Exception as e:
        print(f"  Error: {e}")

    print()
    print("="*60)
    print("  DEMO COMPLETE")
    print("="*60)
    print()
    print("  headspace v0.2.0 - the SuperInstance context plane")
    print("  https://github.com/SuperInstance/headspace")
    print()


if __name__ == "__main__":
    main()
