"""headspace - the SuperInstance context compression plane.

Headspace is the swarm-managed, self-optimizing context compression layer
for the SuperInstance fleet. It combines:

- headroom proxy (context compression)
- ternary swarm (policy optimization)
- baton system (fleet coordination)
- forgemaster protocol (agent operating contract)

Install:
    pip install headspace

Use:
    headspace init
    headspace proxy start
    headspace swarm start
"""

from __future__ import annotations
import logging

__version__ = "0.2.0"
__app_name__ = "headspace"
__all__ = ["__version__", "__app_name__", "install_extension", "compress_for_prompt"]

log = logging.getLogger("headspace")


def install_extension(app, config):
    """Headroom proxy extension entry-point for headspace.
    
    Registers the SuperInstance middleware that compresses GC ledger,
    swarm state, and baton fleet context into every LLM request.
    """
    from headspace._extension import SuperInstanceMiddleware
    from starlette.middleware.base import BaseHTTPMiddleware
    
    app.add_middleware(BaseHTTPMiddleware, cls=SuperInstanceMiddleware)
    log.info("headspace middleware registered (v%s)", __version__)


def compress_for_prompt():
    """Return a compressed context string for prompt injection.
    
    Combines GC ledger state, swarm policy, and baton fleet context
    into a single compact token string the LLM can read.
    """
    parts = []
    
    # GC ledger
    from headspace._extension import _compress_gc_ledger
    gc = _compress_gc_ledger()
    if gc:
        parts.append(gc)
    
    # Swarm
    from headspace.swarm.server import advise
    rec = advise()
    if rec.get("status") == "converged":
        r = rec["recommendation"]
        parts.append(f"<<SWARM set:{r['setpoint']} db:{r['deadband']} il:{r['integral_limit']} kb:{r['kd_boost']}>>")
    else:
        parts.append("<<SWARM: not converged>>")
    
    # Baton
    from headspace.baton.bridge import fleet_context
    parts.append(fleet_context())
    
    # Forge context
    from headspace.forge.context import forge_snapshot
    f = forge_snapshot()
    if f:
        parts.append(f)
    
    return "\n".join(parts)
