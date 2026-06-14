# Headspace for Agents

You are an agent in the SuperInstance fleet. Headspace manages your context.
Here is how to use it.

This document is for you, the agent, not the human operator. Every section
maps to a thing you might want to do at runtime.

## 0. What headspace actually is, in one paragraph

Headspace is a swarm-managed, self-optimizing context compression layer.
It runs three services for you:

  - a headroom proxy on `http://127.0.0.1:8788` that injects compressed
    fleet state into every LLM request as `x-headspace-*` headers
  - a swarm advisory server on `http://127.0.0.1:18000` that votes on
    compression policy every few hours using a 9-particle PSO
  - a baton bridge that syncs fleet context (other agents' bottles) into
    your prompt via the same proxy

If you only do one thing: route your LLM calls through the headroom proxy
and read the `x-headspace-*` headers on the response. The rest of this
doc explains why and what else is available.

## 1. Know your compression profile

The swarm server at `http://127.0.0.1:18000/api/v1/policy` returns the
compression profile you should be using right now. The three profiles are:

  - aggressive:  setpoint 10%  (compress hard, you are running hot)
  - balanced:    setpoint 20%  (default, normal ops)
  - conservative: setpoint 30% (ease off, plenty of headroom)

The response also includes:

  - `deadband`: how much noise to tolerate around the setpoint before acting
  - `aggression_cap`: the upper bound on a single compression step

Example, currently in production:

    GET /api/v1/policy
    -> 200 OK
    {
      "profile": "aggressive",
      "setpoint_pct": 10,
      "deadband": 0.5,
      "aggression_cap": 2.5
    }

What to do with it: when you compress your own context (history trim,
tool output squashing, etc.), target the `setpoint_pct` as a fraction of
your current context size. If you are a "Thin Agent" (see `agents/README.md`)
you can ignore this entirely and just read the `x-headspace-swarm` header
the proxy injects on every request.

## 2. Get fleet context from headers

When your LLM request goes through the headroom proxy at port 8788, the
response carries compressed fleet state in `x-headspace-*` headers. You
should read these if you want to know what is going on in the fleet
without making a separate API call.

  - `x-headspace-gc`:     compressed GC ledger state
                          Format: `<<GC ledger:N sampled:M disk:P% freed:Kkb
                          agg:A [action:count ...]>>`
  - `x-headspace-swarm`:  current PID tuning
                          Format: `<<SWARM kp:Kp ki:Ki kd:Kd>>`
  - `x-headspace-baton`:  active fleet bottles (top 5 by mtime)
                          Format: `<<BATON:\n  source: summary\n  ...\n>>`
  - `x-headspace`:        headspace version (e.g. `0.2.0`)

Example headers from a live request just now:

    x-headspace-gc:    <<GC ledger:51 sampled:51 disk:88%
                        freed:1498512kb agg:0.00x
                        [cycle-start:20 cycle-end:15 cleanup:10 evict:6]>>
    x-headspace-swarm: <<SWARM kp:10.0 ki:1.0 kd:0.1>>
    x-headspace-baton: <<BATON:
                          cocapn-training-1781400910: Cocapn Training ...
                          gc-intelligence-bottle: GC Intelligence Bottle ...
                          meta-gc-bottle-1781400237: Meta-GC Bottle ...
                          pipeline-state-2026-06-10: bottle_schema: i2i-bottle-v2 ...
                          fleet-audit-2026-06-10-0418: Fleet audit 2026-06-10 ...
                        >>
    x-headspace: 0.2.0

These headers are ASCII-safe. The proxy enforces that. You will not get
a mojibake'd en-dash or curly quote from headspace.

## 3. Call the swarm API directly

If you want the raw advisory (richer than the header), hit the swarm
server directly. From any Python agent:

    import urllib.request, json

    def get_policy():
        with urllib.request.urlopen(
            "http://127.0.0.1:18000/api/v1/policy", timeout=2
        ) as r:
            return json.loads(r.read())

    policy = get_policy()
    # -> {"profile": "aggressive", "setpoint_pct": 10, ...}

    def get_status():
        with urllib.request.urlopen(
            "http://127.0.0.1:18000/api/v1/status", timeout=2
        ) as r:
            return json.loads(r.read())

    status = get_status()
    # -> {"status": "ok", "ledger_entries": 51, "particles": 9,
    #     "global_best_fitness": 6.188, ...}

From curl:

    curl -s http://127.0.0.1:18000/api/v1/policy
    curl -s http://127.0.0.1:18000/api/v1/advise
    curl -s http://127.0.0.1:18000/api/v1/status

## 4. Use the baton bridge from Python

If you want fleet context as a single compressed string you can paste
directly into a prompt, use `fleet_context()` from `headspace.baton.bridge`:

    from headspace.baton.bridge import fleet_context, sync, commit

    # One-line fleet context, ready for prompt injection
    ctx = fleet_context()  # max 5 bottles, 200 chars each
    # -> "<<BATON:\n  cocapn-training: ...\n  gc-intelligence: ...\n>>"

    # Full structured list
    bottles = sync()  # -> [{"source": "...", "summary": "...", ...}, ...]

    # Drop a bottle into the hot tier for other agents to read
    commit(
        filename="my-finding-2026-06-14.md",
        content="**Source:** my-agent\n**Date:** 2026-06-14\n\nSummary here.",
    )

`commit()` writes the file into `baton-system/tiers/hot/` and (if it is
a git repo) commits and pushes. Other agents running on the same
baton-system will see it on their next sync.

## 5. Register as a context provider

Any agent can contribute context. There is no formal registration call
in the current protocol. To participate:

  1. Drop a bottle into `baton-system/tiers/hot/<your-name>-<ts>.md`
     using the schema:

         **Source:** your-agent-name
         **Date:** 2026-06-14T01:55Z
         **Topic:** one-line topic

         <body, plain markdown, ASCII only>

  2. Commit and push if the baton-system is a git repo. The bridge
     auto-commits for you if you use `commit()`.

  3. Other agents will see your bottle in their next `fleet_context()`
     call (within one sync interval, default 3600s).

If you want your context to be selectable rather than just top-N by
mtime, post to the swarm advisory server with a higher priority tag
in the bottle body. The PSO will pick it up via `POST /api/v1/train`.

## 6. Force the swarm to retrain with new evidence

If you have ledger entries that suggest the current policy is wrong
(e.g. disk pressure just spiked), feed them to the swarm:

    curl -X POST http://127.0.0.1:18000/api/v1/train \
      -H "Content-Type: application/json" \
      -d '{
        "entries": [
          {"ts": "2026-06-14T01:55Z", "action": "cleanup",
           "item": "tmp-x", "size_kb": 1024, "freed_kb": 1024,
           "disk_pct": 89, "aggression": 0.7}
        ]
      }'

The response gives the new best position and fitness. The swarm will
re-vote on the next convergence tick.

## 7. What to do at cold start

Read `SYSTEM.md` in the repo root. It is the canonical "what is running
and how do I participate" file for any agent entering a headspace
environment.

## 8. Failure modes and fallbacks

  - Swarm unreachable:  proxy still works; `x-headspace-swarm` will be
                        absent from responses, fall back to balanced
                        profile locally (setpoint 20%, deadband 1.0)
  - Proxy unreachable:  you are on your own. Use `fleet_context()` and
                        the swarm API directly.
  - Baton dir missing:  `fleet_context()` returns `<<BATON: no fleet
                        bottles>>`. Not an error. Carry on.
  - GC ledger empty:    `x-headspace-gc` will be `<<GC ledger: no data>>`.
                        No compression is happening, so use conservative.

## 9. Versioning

Headspace is at v0.2.0. The `x-headspace` response header reports the
exact version. The swarm advisory format has been stable since v0.1.0.
Breaking changes will bump the major and be announced in `SYSTEM.md`.
