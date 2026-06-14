# Headspace

**The swarm-managed, self-optimizing context plane for AI agents.**

Headspace turns headroom from a static compression proxy into an **autonomous, self-governing context management system** that optimizes itself via swarm intelligence, coordinates across a fleet via baton bottles, and self-heals via forgemaster protocol.

## What makes it a killer app

| What | How headspace does it |
|------|----------------------|
| **Context compression** | Headroom proxy + SuperInstance schema encoder compresses 10KB GC ledger → 298 chars (3.3%) |
| **Self-optimizing** | Ternary swarm (9 particles on {-1,0,+1} grid) votes on compression policy every 4h |
| **Fleet-aware** | Baton bridge syncs context across all SuperInstance machines |
| **Self-healing** | Forgemon protocol validates system state at boot; warns on drift |
| **One command deploy** | `pip install headspace && headspace init && headspace proxy start` |
| **Works on ARM64** | No onnx, no GPU needed — pure Python + Starlette |

## Quick start

```bash
pip install headspace

# Initialize — creates config, verifies deps, tests proxy
headspace init

# Start the context compression proxy (port 8788)
headspace proxy start

# Start the swarm advisory server (port 8765)
headspace swarm start

# Check everything
headspace status
```

## What you get

```
headspace proxy start (port 8788)
  → Headroom proxy with SuperInstance extension
  → Every LLM request gets compressed fleet context injected as headers
  → x-headroom-gc: "<<GC ledger:51 disk:88% freed:1498512kb ag:0.5>>
  → x-headroom-swarm: "<<SWARM kp:10.0 ki:1.0 kd:0.1>>""
  → x-headroom-baton: "<<BATON: ...5 bottles...>>"

headspace swarm start (port 8765)
  → Swarm advisory API
  → GET /api/v1/advise — current recommendation
  → GET /api/v1/status — particle positions, fitness scores
  → GET /api/v1/policy — compression policy (aggressive/balanced/conservative)
  → POST /api/v1/train — feed new ledger entries, trigger convergence
```

## Commands

```
headspace init              Create config, verify dependencies
headspace status            Show fleet state (proxy, swarm, GC, disk, baton)
headspace proxy start       Start headroom proxy
headspace proxy stop        Stop it
headspace proxy status      Proxy health check
headspace swarm start       Start swarm advisory server
headspace swarm status      Particle positions, convergence state
headspace baton sync        Force fleet bottle read
headspace compress <file>   Test compression on any file
```

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  headspace CLI                       │
├─────────────────────────────────────────────────────┤
│                                                      │
│  headroom proxy (port 8788)                          │
│  ├── SuperInstance extension                         │
│  │   ├── GC ledger → 3.3% tokens                     │
│  │   ├── Swarm state → 60-char vote                  │
│  │   ├── Baton bottles → fleet context                │
│  │   └── Forge state → cold-start bootstrap          │
│  │                                                    │
│  ├── swarm server (port 8765)                        │
│  │   ├── GET /api/v1/advise                          │
│  │   ├── GET /api/v1/status                          │
│  │   ├── GET /api/v1/policy                          │
│  │   └── POST /api/v1/train                          │
│  │                                                    │
│  └── baton bridge                                    │
│      ├── sync() → read hot-tier bottles               │
│      ├── commit() → write new bottles                 │
│      └── fleet_context() → prompt-ready string        │
│                                                        │
│  Oracle2 subsystem integration:                       │
│  ├── gc-pid-bridge (Rust, Kp=10.0 Ki=1.0 Kd=0.1)    │
│  ├── ternary-gc-advisor (9-particle PSO)             │
│  ├── meta-gc-agent (PID auto-adjust, cron every 4h)  │
│  └── baton-system (fleet coordination via git)       │
│                                                        │
└─────────────────────────────────────────────────────┘
```

## Real-world metrics (Oracle2, running now)

| Metric | Value |
|--------|-------|
| GC ledger entries | 51 |
| Compression ratio | 3.3% (10KB → 298 chars) |
| Swarm fitness | 6.188 |
| PID constants | Kp=10.0 Ki=1.0 Kd=0.1 |
| Disk | 45G, 88% used, 5.8G free |
| Total reclaimed | 1.5 GB |
| Bottles in flight | 5 |
| Boot to recovery | 0 |

## Related

- [Headroom](https://github.com/SuperInstance/headroom) — context compression proxy
- [gc-pid-bridge](https://github.com/SuperInstance/gc-pid-bridge) — PID control
- [baton-system](https://github.com/SuperInstance/baton-system) — fleet coordination
- [forgemaster-shell](https://github.com/SuperInstance/forgemaster-shell) — agent protocol
- [ternary-swarm](https://github.com/SuperInstance/ternary-swarm) — Boid/ACO/PSO

## License

MIT
