"""HeadspaceAgent - the runtime SDK that makes agents headspace-dependent.

Inherit from this class and get:
- Auto-compressed context
- Fleet-aware state
- Swarm-optimized compression policy
- Automatic baton sync

Usage:
    class MyAgent(HeadspaceAgent):
        def on_tick(self, context, fleet):
            # context is pre-compressed
            # fleet has baton state
            return "act"

    agent = MyAgent("claude-1")
    while True:
        action = agent.tick()
        time.sleep(1)
"""

import json
import logging
import os
import shutil
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger("headspace.agent")

DEFAULT_SWARM_URL = os.environ.get(
    "HEADSPACE_SWARM_URL", "http://127.0.0.1:8765"
)
DEFAULT_WORKSPACE = Path(
    os.environ.get("HEADSPACE_WORKSPACE", str(Path.home() / ".openclaw" / "workspace"))
)


@dataclass
class SwarmPolicy:
    """Current compression policy from the swarm."""

    profile: str = "balanced"
    setpoint_pct: int = 20
    deadband: float = 1.0
    aggression_cap: float = 2.0
    integral_limit: float = 20.0
    fitness: float = 0.0
    fetched_at: float = 0.0

    @property
    def is_stale(self) -> bool:
        """Policy is stale after 1 hour."""
        return time.time() - self.fetched_at > 3600

    @property
    def age_seconds(self) -> float:
        return max(0.0, time.time() - self.fetched_at)


@dataclass
class FleetContext:
    """Compressed fleet state from baton bridge."""

    bottles: list = field(default_factory=list)
    gc_ledger_summary: str = ""
    disk_gb_total: float = 0.0
    disk_gb_free: float = 0.0
    disk_pct_used: float = 0.0
    fetched_at: float = 0.0

    @property
    def is_stale(self) -> bool:
        return time.time() - self.fetched_at > 3600


class HeadspaceAgent:
    """Base class for headspace-aware agents.

    Subclass and override ``on_tick`` to add behavior. The base class
    handles policy sync, fleet sync, context compression, and prompt
    injection automatically.

    Args:
        agent_id: Unique identifier for this agent in the fleet.
        swarm_url: Base URL of the headspace swarm server.
        workspace: Path to the OpenClaw workspace root.
        auto_sync_interval: Seconds between background syncs.
    """

    def __init__(
        self,
        agent_id: str,
        swarm_url: str = DEFAULT_SWARM_URL,
        workspace: Optional[Path] = None,
        auto_sync_interval: int = 300,
    ):
        self.agent_id = agent_id
        self.swarm_url = swarm_url.rstrip("/")
        self.workspace = Path(workspace) if workspace else DEFAULT_WORKSPACE
        self._policy: Optional[SwarmPolicy] = None
        self._fleet: Optional[FleetContext] = None
        self._last_sync: float = 0.0
        self._auto_sync_interval = auto_sync_interval
        self._tick_count: int = 0
        self._started_at: float = time.time()

        # Warmup: fetch policy and fleet on init (graceful if offline)
        self.sync_policy()
        self.sync_fleet()

    # ---------------------------------------------------------------- sync

    def sync_policy(self) -> SwarmPolicy:
        """Fetch current compression policy from the swarm server.

        On any error, retains the existing policy or falls back to defaults.
        """
        try:
            resp = urllib.request.urlopen(
                f"{self.swarm_url}/api/v1/policy", timeout=5
            )
            data = json.loads(resp.read().decode("utf-8"))
            self._policy = SwarmPolicy(
                profile=data.get("profile", "balanced"),
                setpoint_pct=data.get("setpoint_pct", 20),
                deadband=data.get("deadband", 1.0),
                aggression_cap=data.get("aggression_cap", 2.0),
                integral_limit=data.get("integral_limit", 20.0),
                fitness=data.get("fitness", 0.0),
                fetched_at=time.time(),
            )
            log.info(
                "policy synced: profile=%s setpoint=%s fitness=%.2f",
                self._policy.profile,
                self._policy.setpoint_pct,
                self._policy.fitness,
            )
        except (urllib.error.URLError, json.JSONDecodeError, KeyError, OSError) as e:
            log.warning("policy fetch failed (%s); using cached/default", e)
            if self._policy is None:
                self._policy = SwarmPolicy()
        return self._policy

    def sync_fleet(self) -> FleetContext:
        """Fetch fleet state from baton bridge (local filesystem).

        Disk + GC ledger + hot bottles. Never raises - returns best effort.
        """
        ctx = FleetContext(fetched_at=time.time())
        try:
            disk = shutil.disk_usage(str(self.workspace))
            ctx.disk_gb_total = disk.total / 1e9
            ctx.disk_gb_free = disk.free / 1e9
            ctx.disk_gb_used = disk.used / 1e9
            ctx.disk_pct_used = disk.used / disk.total * 100.0

            ledger = self.workspace / "data" / "gc-ledger" / "ledger.jsonl"
            if ledger.exists():
                lines = [
                    l.strip()
                    for l in ledger.read_text(encoding="utf-8", errors="replace").splitlines()
                    if l.strip().startswith("{")
                ]
                if lines:
                    try:
                        last = json.loads(lines[-1])
                        ctx.gc_ledger_summary = (
                            f"entries:{len(lines)} "
                            f"disk:{last.get('disk_pct', '?')}%"
                        )
                    except json.JSONDecodeError:
                        ctx.gc_ledger_summary = f"entries:{len(lines)}"

            hot_dir = self.workspace / "baton-system" / "tiers" / "hot"
            if hot_dir.exists():
                ctx.bottles = sorted(
                    [b.stem for b in hot_dir.glob("*.md")],
                    reverse=True,
                )
        except Exception as e:  # noqa: BLE001 - best-effort sync
            log.warning("fleet sync error: %s", e)

        self._fleet = ctx
        self._last_sync = time.time()
        return ctx

    # ------------------------------------------------------------ compress

    def compress_context(self, context: str) -> str:
        """Compress a context string using current swarm policy profile.

        Profile routing:
            - aggressive:   strip comments, truncate long prompts
            - conservative: dedup-adjacent only, cap line length
            - balanced:     dedup exact lines
        """
        if not context or self._policy is None:
            return context

        profile = self._policy.profile
        if profile == "aggressive":
            return self._aggressive_compress(context)
        if profile == "conservative":
            return self._conservative_compress(context)
        return self._balanced_compress(context)

    def _aggressive_compress(self, text: str) -> str:
        """Aggressive: strip comments, truncate long system prompts."""
        result = []
        for raw in text.splitlines():
            s = raw.strip()
            if not s:
                continue
            # Drop non-critical comments
            if s.startswith("#") and "important" not in s.lower():
                continue
            # Truncate very long prompt-like lines
            if len(s) > 200 and "you are" in s[:30].lower():
                s = s[:150] + "...[truncated]"
            result.append(s)
        return "\n".join(result)

    def _balanced_compress(self, text: str) -> str:
        """Balanced: dedup exact lines, drop blank lines."""
        seen = set()
        result = []
        for raw in text.splitlines():
            s = raw.strip()
            if not s or s in seen:
                continue
            seen.add(s)
            result.append(s)
        return "\n".join(result)

    def _conservative_compress(self, text: str) -> str:
        """Conservative: only cap very long lines."""
        result = []
        for raw in text.splitlines():
            s = raw.strip()
            if not s:
                continue
            if len(s) > 500:
                s = s[:480] + "...[+truncated]"
            result.append(s)
        return "\n".join(result)

    # --------------------------------------------------------- prompt bits

    def fleet_string(self) -> str:
        """Compact ASCII string of fleet state for prompt injection."""
        if self._fleet is None:
            self.sync_fleet()
        assert self._fleet is not None
        f = self._fleet
        parts = [f"<<FLT d:{f.disk_pct_used:.0f}% f:{f.disk_gb_free:.1f}G>>"]
        if f.gc_ledger_summary:
            parts.append(f"<<GC {f.gc_ledger_summary}>>")
        if f.bottles:
            parts.append(f"<<BAT {len(f.bottles)} btl>>")
        if self._policy is not None and self._policy.fitness:
            parts.append(
                f"<<POL pro:{self._policy.profile} fit:{self._policy.fitness:.1f}>>"
            )
        return " ".join(parts)

    def build_prompt(self, system: str, user: str) -> str:
        """Build a complete agent prompt with headspace context injected.

        The result is ASCII-safe and self-delimited with <FLT>...</FLT> tags.
        """
        fleet = self.fleet_string()
        policy_str = ""
        if self._policy is not None:
            policy_str = (
                f"<<POL set:{self._policy.setpoint_pct}% "
                f"db:{self._policy.deadband} "
                f"cap:{self._policy.aggression_cap}x>>"
            )
        compressed_system = self.compress_context(system)
        return (
            f"<FLT>{fleet} {policy_str}</FLT>\n\n"
            f"{compressed_system}\n\n{user}"
        )

    # ------------------------------------------------------------ lifecycle

    def tick(self) -> Optional[str]:
        """Called on each agent tick. Override ``on_tick`` in subclass.

        Returns:
            str action from ``on_tick`` or None to idle.
        """
        self._tick_count += 1

        # Auto-resync if stale
        if time.time() - self._last_sync > self._auto_sync_interval:
            self.sync_policy()
            self.sync_fleet()

        try:
            return self.on_tick(
                self.compress_context(str(self)), self.fleet_string()
            )
        except Exception as e:  # noqa: BLE001 - keep agent alive
            log.error("tick error for %s: %s", self.agent_id, e)
            return None

    def on_tick(self, context: str, fleet: str) -> Optional[str]:
        """Override in your agent subclass.

        Args:
            context: Self-serialized (compressed) agent state.
            fleet:   Compact fleet state string.

        Returns:
            Action string or None to idle.
        """
        return None

    @property
    def uptime(self) -> float:
        return time.time() - self._started_at

    @property
    def policy(self) -> Optional[SwarmPolicy]:
        return self._policy

    @property
    def fleet(self) -> Optional[FleetContext]:
        return self._fleet

    def __repr__(self) -> str:
        return (
            f"HeadspaceAgent(id={self.agent_id!r} "
            f"ticks={self._tick_count} uptime={self.uptime:.1f}s)"
        )


# ------------------------------------------------- procedural convenience API


def fleet_state(swarm_url: str = DEFAULT_SWARM_URL) -> str:
    """One-shot: get a compact fleet state string for prompt injection.

    Usage:
        sys_prompt = "..." + fleet_state()
    """
    agent = HeadspaceAgent("anonymous", swarm_url=swarm_url)
    return agent.fleet_string()


def compress(text: str, profile: str = "balanced") -> str:
    """One-shot context compression based on profile.

    Usage:
        compressed = compress(raw_context, profile="aggressive")
    """
    agent = HeadspaceAgent("anonymous")
    agent._policy = SwarmPolicy(profile=profile, fetched_at=time.time())
    return agent.compress_context(text)


def policy(swarm_url: str = DEFAULT_SWARM_URL) -> dict:
    """One-shot: get current swarm policy as a dict.

    Usage:
        pol = policy()
    """
    agent = HeadspaceAgent("anonymous", swarm_url=swarm_url)
    p = agent._policy or SwarmPolicy()
    return {
        "profile": p.profile,
        "setpoint_pct": p.setpoint_pct,
        "deadband": p.deadband,
        "aggression_cap": p.aggression_cap,
        "integral_limit": p.integral_limit,
        "fitness": p.fitness,
        "stale": p.is_stale,
    }
