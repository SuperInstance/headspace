"""Swarm advisory HTTP server.

Wraps the existing TernarySwarmAdvisor from scripts/ternary-gc-advisor.py
behind a starlette app with CORS, JSON responses, and runtime state.
"""

import json
import os
import sys
import time
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger("headspace.swarm")

WORKSPACE = Path(os.environ.get("HEADSPACE_WORKSPACE", str(Path.home() / ".openclaw" / "workspace")))

# Import the existing advisor code
ADVISOR_PATH = WORKSPACE / "scripts" / "ternary-gc-advisor.py"
ADVISOR_AVAILABLE = False
TernarySwarmAdvisor = None  # type: ignore
if ADVISOR_PATH.exists():
    sys.path.insert(0, str(WORKSPACE / "scripts"))
    try:
        import ternary_gc_advisor  # type: ignore
        TernarySwarmAdvisor = ternary_gc_advisor.TernarySwarmAdvisor  # type: ignore
        ADVISOR_AVAILABLE = True
    except (ImportError, AttributeError) as e:
        log.warning("Could not import TernarySwarmAdvisor: %s", e)


def advise() -> dict:
    """Return the current swarm recommendation."""
    if not ADVISOR_AVAILABLE:
        return {"status": "advisor_unavailable", "fallback": {
            "setpoint": 20, "deadband": 1.0, "integral_limit": 20.0, "kd_boost": 0.2
        }}
    advisor = TernarySwarmAdvisor()  # type: ignore
    return advisor.recommend()


def status() -> dict:
    """Return swarm runtime status."""
    if not ADVISOR_AVAILABLE:
        return {"status": "advisor_unavailable", "particles": 0, "fitness": 0}
    advisor = TernarySwarmAdvisor()  # type: ignore
    n = advisor.load_ledger()
    best, fitness = advisor.converge(max_iter=10)
    return {
        "status": "ok" if n >= 3 else "insufficient_data",
        "ledger_entries": n,
        "particles": len(advisor.particles),
        "particle_positions": [p["pos"] for p in advisor.particles],
        "global_best_fitness": fitness,
        "global_best_pos": best,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def policy() -> dict:
    """Return the recommended compression policy as a flat config."""
    rec = advise()
    if rec.get("status") != "converged":
        return {
            "profile": "balanced",
            "setpoint_pct": 20,
            "deadband": 1.0,
            "aggression_cap": 5.0,
        }
    r = rec["recommendation"]
    setpoint = r["setpoint"]
    if setpoint <= 12:
        profile = "aggressive"
    elif setpoint >= 25:
        profile = "conservative"
    else:
        profile = "balanced"
    return {
        "profile": profile,
        "setpoint_pct": setpoint,
        "deadband": r["deadband"],
        "aggression_cap": max(r["integral_limit"] / 4.0, 2.0),
    }


class SwarmServer:
    """Starlette app for the swarm advisory server."""
    
    def __init__(self, port: int = 8765):
        self.port = port
        
    def build_app(self):
        try:
            from starlette.applications import Starlette
            from starlette.routing import Route, Mount
            from starlette.responses import JSONResponse
            from starlette.middleware.cors import CORSMiddleware
        except ImportError:
            log.error("starlette not installed")
            raise
        
        async def advise_route(request):
            return JSONResponse(advise())
        
        async def status_route(request):
            return JSONResponse(status())
        
        async def policy_route(request):
            return JSONResponse(policy())
        
        async def health_route(request):
            return JSONResponse({"status": "ok", "service": "headspace-swarm"})
        
        async def train_route(request):
            try:
                body = await request.json()
                entries = body.get("entries", [])
                if not ADVISOR_AVAILABLE:
                    return JSONResponse({"status": "advisor_unavailable"}, status_code=503)
                advisor = TernarySwarmAdvisor()  # type: ignore
                advisor.ledger = entries
                best, fitness = advisor.converge()
                return JSONResponse({
                    "status": "trained",
                    "entries": len(entries),
                    "fitness": fitness,
                    "best_pos": best,
                })
            except Exception as e:
                return JSONResponse({"error": str(e)}, status_code=400)
        
        routes = [
            Route("/api/v1/advise", advise_route),
            Route("/api/v1/status", status_route),
            Route("/api/v1/policy", policy_route),
            Route("/api/v1/train", train_route, methods=["POST"]),
            Route("/healthz", health_route),
        ]
        
        app = Starlette(routes=routes)
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
        return app
    
    def run(self):
        import uvicorn
        app = self.build_app()
        uvicorn.run(app, host="127.0.0.1", port=self.port, log_level="info")



def main():
    """Entry point for headspace swarm start."""
    SwarmServer(port=int(os.environ.get("HEADSPACE_SWARM_PORT", "8765"))).run()


if __name__ == "__main__":
    main()
