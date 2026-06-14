# Headspace

**The swarm-managed context compression plane for the SuperInstance fleet.**

Headspace turns Headroom (context compression) from a static tool into a
self-optimizing killer app. Install it once, and every LLM call automatically
gets the smallest possible context that still carries all your fleet state.

```
pip install headspace
headspace init
headspace proxy start
```

That's it. Your agents now share a fleet-aware, swarm-tuned context budget.

---

## The Problem

Every LLM application eats tokens for breakfast:
- System prompts: 500+ tokens
- Conversation history: 1000+ tokens
- Fleet state, GC logs, swarm votes, baton bottles: 2000+ tokens
- Tool descriptions: 1000+ tokens

You either **pay for it**, **drop context**, or **build brittle compression** yourself.

## The Solution

Headspace layers three independent systems into one pipe:

1. **Headroom proxy** — compresses the upstream LLM request in flight
2. **Ternary swarm** — votes on the *policy* (aggressive vs balanced vs conservative)
3. **Baton fleet sync** — keeps the agent aware of what other agents are doing

The swarm tunes the policy from your real GC ledger data. If your fleet
runs hot, the swarm goes aggressive. If it's calm, the swarm relaxes.

---

## Quick Start

```bash
pip install headspace

# Initialize (validates components, writes config, tests)
headspace init

# Start the headroom proxy on :8788 with our extension
headspace proxy start

# In a second terminal: start the swarm advisory server
headspace swarm start

# Check the state of everything
headspace status
```

Point your LLM client at `http://127.0.0.1:8788` and you're done.

---

## The Three Layers

### Layer 1: Headroom (compression)

Headroom is a proxy that sits between your agent and the upstream LLM. It:
- Reads the system prompt and tool definitions
- Compresses them via the Kompress ONNX model
- Forwards the request with the same shape, fewer tokens

Headspace adds a **schema-aware** encoder on top: GC ledger entries, swarm
votes, and baton bottles get compressed to 3-12% of their original size
without losing structure.

| Data | Raw | Compressed | Ratio |
|------|-----|------------|-------|
| GC ledger (50 entries) | ~10 KB | ~300 chars | **3.0%** |
| Swarm state | ~500 B | ~60 chars | 12% |
| Baton bottles (5) | ~10 KB | ~600 chars | 6% |

### Layer 2: Ternary Swarm (policy)

A 9-particle PSO over the policy grid `{-1, 0, +1}`. The swarm votes on:
- **setpoint**: target disk % free (10 / 20 / 30)
- **deadband**: how tight the target is (0.5 / 1.0 / 2.0)
- **integral_limit**: how aggressive the integral term can get
- **kd_boost**: how anticipatory the derivative term is

The swarm converges on the policy that produced the best outcomes in the
real GC ledger. It runs as a real HTTP server (starlette + uvicorn) with:

- `GET  /api/v1/advise` — current recommendation
- `POST /api/v1/train` — train on new ledger data
- `GET  /api/v1/status` — particle positions, fitness
- `GET  /api/v1/policy` — the recommended profile (aggressive/balanced/conservative)

### Layer 3: Baton Fleet Sync

Baton is the fleet coordination protocol. Headspace reads the **hot tier**
of `baton-system/tiers/hot/*.md` and produces a compressed fleet context
that gets injected into every prompt. When another agent posts a bottle
("GC ran, reclaimed 1.2 GB"), your agent sees it.

---

## Killer App Features

### One-command deploy

```
headspace init && headspace proxy start
```

Validates components, writes proxy config, starts the proxy. Done.

### Self-tuning

The swarm watches your GC ledger and tunes the compression policy. No
human in the loop. When you go from 12% disk free to 5%, the swarm
shifts to aggressive mode. When you stabilize, it relaxes.

### Fleet-aware

Any agent on the fleet can read the baton hot tier. Headspace makes
this automatic. Your agent's context always reflects what other agents
are doing, in 200 characters.

### Schema-aware compression

GC ledger entries compress to a fixed-schema string:
`<<GC:50 d:88% f:1498512kb s:cycle>>` — 35 chars for a 9 KB entry.

### Forgemaster-compatible

Headspace speaks the Forgemaster protocol. Run `headspace forge` to
check that all required components are present.

---

## Architecture

```
your agent (Claude, GPT, local LLM)
        |
        v
+------------------+
|  headroom proxy  |  :8788
|  + superinstance |
|    extension     |
+--------+---------+
         |
         | HTTP request
         v
+------------------+     +-------------------+
| ternary swarm    |<--->| gc-ledger (JSONL) |
| :8765            |     | (real outcomes)   |
| 9-particle PSO   |     +-------------------+
+--------+---------+
         |
         | policy updates
         v
+------------------+
| baton fleet sync |
| tiers/hot/*.md   |
+------------------+
```

---

## CLI

```
headspace init           # Validate + configure
headspace status         # Show health of all components
headspace proxy start    # Start headroom proxy
headspace proxy stop     # Stop it
headspace swarm start    # Start swarm advisory server
headspace swarm status   # Show particle positions, fitness
headspace baton-sync     # Force fleet sync
headspace compress FILE  # Compress a file
headspace forge          # Forgemaster protocol check
```

---

## Python API

```python
from headspace.swarm import advise, status
from headspace.baton import fleet_context, sync, commit

# What should the GC do?
rec = advise()
print(rec["recommendation"])  # {setpoint: 10, deadband: 0.5, ...}

# What's the fleet doing?
ctx = fleet_context(max_bottles=5)
print(ctx)  # <<BATON: ...>>

# Compress GC ledger directly
from headroom_superinstance import _compress_gc_ledger
gc = _compress_gc_ledger()
print(gc)  # <<GC:50 d:88% f:1498512kb ...>>
```

---

## Installation

```bash
pip install headspace
```

Or from source:

```bash
git clone https://github.com/SuperInstance/headspace
cd headspace
pip install -e .
```

### Requirements

- Python 3.10+
- `starlette`, `uvicorn` (HTTP server)
- `headroom-ai>=0.25` (the proxy)
- `headroom-superinstance` (our schema-aware extension)
- ARM64: works, no ONNX dependency at runtime

---

## Related

- [Headroom fork](https://github.com/SuperInstance/headroom) — context compression proxy
- [gc-pid-bridge](https://github.com/SuperInstance/gc-pid-bridge) — PID control
- [baton-system](https://github.com/SuperInstance/baton-system) — fleet coordination
- [forgemaster-shell](https://github.com/SuperInstance/forgemaster-shell) — agent protocol
- [ternary-swarm](https://github.com/SuperInstance/ternary-swarm) — Boid/ACO/PSO

## License

MIT.
