# Headspace

Context compression + ternary swarm + baton fleet: the **SuperInstance integration hub**.

Headspace brings together four independent innovations into one unified layer:

| Component | Role | Status |
|-----------|------|--------|
| **Headroom** | Context compression proxy (GC ledger → 3.3% of original) | ✅ Forked & adapted |
| **Ternary Swarm** | 9-particle PSO on {-1,0,+1} grid for GC policy | ✅ Built & deployed |
| **Baton System** | Fleet coordination via bottles, splines, shards | ✅ Active |
| **Forgemaster** | Agent operating protocol (commit · parallel · evidence) | ✅ Integrated |

## The thesis

Three independent groups (Neo, Baton, Forgemaster) built overlapping paradigms for:
- **Intelligent context management** (Headroom compresses; we compress deeper with schema awareness)
- **Self-governing systems** (Swarm vote; our PID adjusts; baton propagates)
- **Agent discipline** (Forgemaster protocol; our GC-baton cycle proves it)

Headspace is where they merge — a single repo with:
1. A headroom **proxy configuration** pre-wired for SuperInstance data types
2. A **swarm server** that advises on context compression policy
3. A **baton bridge** that routes compressed fleet state
4. A **forgemaster protocol** that governs all of it

## Quick start

```bash
pip install headroom-superinstance
headroom proxy --proxy-extension superinstance
```

Or with the full ecosystem:

```bash
bash scripts/meta-gc-agent.sh       # PID auto-adjustment from swarm
bash scripts/gc-intelligent.sh       # Host GC + swarm advisory
bash scripts/forge-apply.sh          # Install protocol wiring
```

## Architecture

```
headroom proxy (context compression)
  ├── SuperInstance extension
  │    ├── GC ledger → 3.3% tokens
  │    ├── Swarm state → 60-char vote
  │    └── Baton bottles → fleet context
  │
  ├── gc-pid-bridge (ternary-pid)
  │    ├── Kp=10.0, Ki=1.0, Kd=0.1
  │    ├── Anti-windup, derivative filter
  │    └── Cascade control
  │
  ├── ternary-gc-advisor (9-particle swarm)
  │    ├── {-1,0,+1} policy grid
  │    ├── Fitness: 6.188
  │    └── Converges on optimal setpoint
  │
  ├── meta-gc-agent (PID auto-target)
  │    ├── Cron every 4h
  │    ├── Adjusts PID from swarm
  │    └── Writes baton bottles
  │
  └── baton-system (fleet protocol)
       ├── Tiers: hot/warm/cold
       ├── Bottles with 3-way shards
       └── Distributed via git
```

## Related

- [Headroom fork](https://github.com/SuperInstance/headroom) — context compression proxy
- [gc-pid-bridge](https://github.com/SuperInstance/gc-pid-bridge) — PID control
- [baton-system](https://github.com/SuperInstance/baton-system) — fleet coordination
- [forgemaster-shell](https://github.com/SuperInstance/forgemaster-shell) — agent protocol
- [ternary-swarm](https://github.com/SuperInstance/ternary-swarm) — Boid/ACO/PSO

## License

MIT — see LICENSE.
