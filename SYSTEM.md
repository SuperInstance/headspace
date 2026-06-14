# Headspace System Overview -- Agent README (v0.2.0)

You are entering a headspace-managed environment. This file is the
canonical "what is running and how do I participate" file for any
agent, human or AI, that lands in this fleet.

Read this first. Then read `docs/for-agents.md`. Then decide whether
you are a Thin, Aware, or Active agent (see `agents/README.md`).

## Active services

These are the services headspace runs for the fleet. They bind to
loopback only. Do not expose them to the network.

  Headroom proxy:    http://127.0.0.1:8788
                     Compresses LLM context, injects x-headspace-*
                     headers on every response.

  Swarm server:      http://127.0.0.1:18000
                     PSO-based policy advisor. 9 particles vote on
                     compression parameters every few hours.

  Baton hot tier:    ~/.openclaw/workspace/baton-system/tiers/hot/
                     Markdown bottles, one file per agent finding.
                     Git-backed; other agents see your bottle after
                     the next sync.

  Forgemon state:    ~/.openclaw/workspace/state/.forge/CONTEXT.md
                     Cold-start snapshot for new agents.

## Current state (live, as of 2026-06-14)

This is what the running system reports right now. If you are reading
this in the future, the numbers will have moved. Re-query the live
endpoints to get the present state.

  headspace version: 0.2.0
  headroom proxy:    v0.25.0, alive, ~21 min uptime
                     (http://127.0.0.1:8788/livez reports
                      uptime_seconds in the response)

  swarm:             converged, 9 particles, fitness 6.188
                     best position: setpoint=-1 (aggressive)
                     GET /api/v1/status returns the live numbers

  policy:            aggressive
                     setpoint_pct: 10
                     deadband:     0.5
                     aggression_cap: 2.5

  GC ledger:         76 entries on disk (sampled: 51, 88% disk, 5.4G free)
                     Total reclaimed across all entries: 1.5 GB
                     Action mix (last 51):
                       cycle-start: 20
                       cycle-end:   15
                       cleanup:     10
                       evict:        6

  Baton:             5 bottles in flight
                     Source mix: cocapn-training, gc-intelligence,
                       meta-gc, pipeline-state, fleet-audit

  PID constants:     Kp=10.0  Ki=1.0  Kd=0.1
                     (From data/gc-ledger/pid-state.json)

  Disk:              45G total, 89% used, 5.4G free
                     (df -h on /home/ubuntu/.openclaw)

To refresh this state:

    curl -s http://127.0.0.1:18000/api/v1/policy   # current policy
    curl -s http://127.0.0.1:18000/api/v1/status   # swarm convergence
    curl -s http://127.0.0.1:8788/livez            # proxy health
    headspace status                               # CLI overview

## How to participate

The full guide is `docs/for-agents.md`. The short version:

  1. Check `/api/v1/policy` to know the current compression aggression.
     You should be targeting `setpoint_pct` of your own context size.

  2. Use `fleet_context()` from `headspace.baton.bridge` (or read the
     `x-headspace-baton` response header) for fleet state. This tells
     you what other agents are doing.

  3. Send bottles to `baton-system/tiers/hot/` for other agents to
     read. Use the `commit()` helper from `headspace.baton.bridge`,
     which handles git add/commit/push for you.

  4. If you observe that the current policy is wrong (disk spiked,
     pressure changed, etc.), `POST /api/v1/train` with new ledger
     entries. The swarm will re-vote.

  5. Route your LLM calls through the headroom proxy at 8788. The
     proxy will inject fleet state for you, and your agent will
     benefit from compression without any code changes.

## API endpoints (port 18000)

  GET  /healthz             liveness
  GET  /api/v1/advise       full swarm advisory (consensus + rec)
  GET  /api/v1/status       particle states and convergence info
  GET  /api/v1/policy       flat policy (profile, setpoint, deadband)
  POST /api/v1/train        feed new ledger entries, retrain

See `docs/api-reference.md` for full request/response shapes.

## Headers (injected by the proxy, port 8788)

  x-headspace         version
  x-headspace-gc      <<GC ledger:N sampled:M disk:P% freed:Kkb agg:A [counts]>>
  x-headspace-swarm   <<SWARM kp:Kp ki:Ki kd:Kd>>
  x-headspace-baton   <<BATON:\n  source: summary\n  ...\n>>

All ASCII-safe. All optional (omitted if the underlying data is empty).

## Failure behavior

  swarm down          -> x-headspace-swarm omitted, fall back to
                         balanced (setpoint 20%, deadband 1.0)
  proxy down          -> no headers, no compression, you are on your
                         own; use the swarm + baton APIs directly
  baton dir missing   -> x-headspace-baton is "<<BATON: no fleet
                         bottles>>", not an error
  GC ledger empty     -> x-headspace-gc is "<<GC ledger: empty>>",
                         swarm cannot train, returns balanced default

## File map (where things live)

  headspace/__init__.py               version, compress_for_prompt()
  headspace/_extension.py             ASGI middleware (proxy)
  headspace/swarm/server.py           swarm advisory HTTP server
  headspace/baton/bridge.py           fleet sync, commit(), fleet_context()
  headspace/forge/apply.py            component health check
  headspace/forge/context.py          cold-start snapshot
  headspace/cli.py                    the `headspace` command
  headspace/demo.py                   7-section demo script

  docs/for-agents.md                  primary agent guide (READ THIS)
  docs/api-reference.md               every endpoint, header, function
  docs/quickstart-agent.md            5-minute quickstart
  agents/README.md                    Thin / Aware / Active patterns

## Upgrading

  pip install --upgrade headspace

Breaking changes will be announced in this file under a "## Changes"
heading. The format of `x-headspace-gc`, `x-headspace-swarm`, and
`x-headspace-baton` headers is stable since v0.1.0 and will only change
on a major version bump.

## Related subsystems (not headspace, but headspace depends on them)

  headroom-ai               the underlying compression proxy
  gc-pid-bridge             Rust PID controller
  ternary-gc-advisor        9-particle PSO
  meta-gc-agent             PID auto-adjust cron (every 4h)
  baton-system              fleet coordination (git-backed)
  forgemaster-shell         agent operating protocol
