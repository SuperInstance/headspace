# Headspace API Reference

Machine-readable reference for every public surface headspace exposes.
If you are an agent and you only have time to read one section, read
"Quick reference card" at the bottom.

All endpoints return JSON. All string fields are ASCII-safe. All
timestamps are ISO-8601 UTC with `Z` suffix. All ports default to
loopback (`127.0.0.1`).

## Swarm Server

Base URL: `http://127.0.0.1:18000` (configurable via `HEADSPACE_SWARM_PORT`
on the server side; the CLI starts it on 18000 by default to avoid
conflict with opensmile on 8765).

### GET /healthz

Liveness probe. Always 200 if the process is up.

Response:

    {
      "status": "ok",
      "service": "headspace-swarm"
    }

### GET /api/v1/advise

Returns the current swarm advisory in full. Heavier than `/policy`:
includes particle consensus, recommendation, and fitness.

Response (200):

    {
      "status": "converged",            // "converged" | "insufficient_data" | "advisor_unavailable"
      "entries": 51,                    // ledger entries the swarm trained on
      "swarm_consensus": {              // human-readable rollup of the 9 particles
        "setpoint":       "aggressive (10%)",
        "deadband":       "narrow (reactive)",
        "integral_limit": "low windup limit",
        "kd_boost":       "weak derivative"
      },
      "recommendation": {               // actual values to apply
        "setpoint":       10,           // % of context to keep
        "deadband":       0.5,
        "integral_limit": 10.0,
        "kd_boost":       0.1,
        "setpoint_desc":       "aggressive (10%)",
        "deadband_desc":       "narrow (reactive)",
        "integral_limit_desc": "low windup limit",
        "kd_boost_desc":       "weak derivative"
      },
      "fitness": 6.1883234042553195
    }

Possible non-200 responses: 200 always (degraded states are signalled
in the `status` field).

### GET /api/v1/status

Returns particle states and convergence info. Use this to decide
whether the swarm is worth trusting yet.

Response (200):

    {
      "status": "ok",                   // "ok" | "insufficient_data" | "advisor_unavailable"
      "ledger_entries": 51,             // number of GC ledger rows loaded
      "particles": 9,                   // PSO particle count (fixed)
      "particle_positions": [           // each particle's current {-1,0,+1}^4 vote
        {"setpoint":-1, "deadband":-1, "integral_limit":-1, "kd_boost":-1},
        ...
      ],
      "global_best_fitness": 6.188,     // lower is better
      "global_best_pos": {"setpoint":-1, ...},
      "timestamp": "2026-06-14T01:55:33Z"
    }

Rule of thumb: if `status` is `insufficient_data` you need at least 3
ledger entries before the swarm has anything to vote on. If
`advisor_unavailable` then `ternary_gc-advisor.py` is not on the
PYTHONPATH and you should fall back to balanced locally.

### GET /api/v1/policy

Returns a flat, easy-to-apply compression policy. This is the endpoint
agents should call most often.

Response (200):

    {
      "profile":        "aggressive",   // "aggressive" | "balanced" | "conservative"
      "setpoint_pct":   10,             // % of context size to keep
      "deadband":       0.5,            // tolerance around setpoint
      "aggression_cap": 2.5             // max single-step compression
    }

Mapping (setpoint -> profile):

    setpoint <= 12        -> "aggressive"
    12 < setpoint < 25    -> "balanced"
    setpoint >= 25        -> "conservative"

When the swarm is not converged the response is the balanced default:

    {"profile":"balanced","setpoint_pct":20,"deadband":1.0,"aggression_cap":5.0}

### POST /api/v1/train

Feed new GC ledger entries to the swarm and trigger a convergence run.

Request body:

    {
      "entries": [
        {
          "ts":         "2026-06-14T01:55:00Z",
          "action":     "cleanup",        // or "evict", "cycle-start", "cycle-end", ...
          "item":       "tmp-x",
          "size_kb":    1024,
          "freed_kb":   1024,
          "disk_pct":   89,
          "aggression": 0.7               // optional, 0.0..1.0
        }
      ]
    }

Response (200):

    {
      "status":  "trained",
      "entries": 1,                       // echo of how many you sent
      "fitness": 6.188,                   // new global best fitness
      "best_pos": {"setpoint":-1, ...}    // new best position
    }

Errors:

    400 {"error": "..."}                  // bad JSON, missing entries
    503 {"status": "advisor_unavailable"} // ternary_gc_advisor not importable

## Headroom Proxy

Base URL: `http://127.0.0.1:8788` (configurable via `HEADROOM_PROXY` env
var on the client side, `--port` on the server side).

### GET /livez

Liveness. Returns 200 always when the proxy is up.

Response:

    {
      "service":  "headroom-proxy",
      "status":   "healthy",
      "alive":    true,
      "version":  "0.25.0",
      "timestamp":"2026-06-14T01:55:38.771823Z",
      "uptime_seconds": 1376.523
    }

### Response headers (added by headspace middleware)

On any successful LLM request through the proxy, headspace injects:

    x-headspace-gc       ASCII-safe compressed GC ledger
    x-headspace-swarm    ASCII-safe compressed swarm PID state
    x-headspace-baton    ASCII-safe compressed baton fleet context
    x-headspace          headspace version (e.g. "0.2.0")

`x-headspace-gc` format:

    <<GC ledger:N sampled:M disk:P% freed:Kkb agg:A.xx
       [action1:count action2:count ...]>>

Example:

    <<GC ledger:51 sampled:51 disk:88% freed:1498512kb agg:0.00x
       [cycle-start:20 cycle-end:15 cleanup:10 evict:6]>>

`x-headspace-swarm` format:

    <<SWARM kp:Kp ki:Ki kd:Kd>>

Example:

    <<SWARM kp:10.0 ki:1.0 kd:0.1>>

`x-headspace-baton` format (multi-line, up to 5 bottles):

    <<BATON:
      <source>: <summary>
      <source>: <summary>
      ...>>

Example:

    <<BATON:
      cocapn-training: Cocapn Training ...
      gc-intelligence: GC Intelligence Bottle ...
    >>

If a section is empty, the corresponding header is omitted from the
response (not set to empty). If you do not see `x-headspace-swarm`,
the swarm is not converged yet.

## Python API

### `headspace.compress_for_prompt()`

Module: `headspace`
Returns: `str`

Returns a single string with the combined GC + swarm + baton + forge
context, ready to paste into a prompt.

    from headspace import compress_for_prompt
    ctx = compress_for_prompt()
    # GC + swarm + baton + forge joined by newlines

### `headspace.baton.bridge.fleet_context(max_bottles=5, max_chars_per=200)`

Module: `headspace.baton.bridge`
Returns: `str`

Compressed fleet context as a single string. Same format as the
`x-headspace-baton` header.

### `headspace.baton.bridge.sync()`

Module: `headspace.baton.bridge`
Returns: `list[dict]`

Reads all hot-tier bottles and returns a list of metadata dicts:

    [
      {
        "filename": "gc-intelligence-bottle.md",
        "path":     "/home/.../baton-system/tiers/hot/gc-intelligence-bottle.md",
        "source":   "gc-intelligence",
        "date":     "2026-06-14 01:33 UTC",
        "summary":  "GC Intelligence Bottle ..."
      },
      ...
    ]

### `headspace.baton.bridge.commit(filename, content, message=None)`

Module: `headspace.baton.bridge`
Returns: `Path` or `None`

Writes `content` to `baton-system/tiers/hot/<filename>`, then `git add`,
`git commit -m <message>`, `git push` if the baton-system is a git
repo. If git is not available, only the file is written.

### `headspace.forge.apply.check_components()`

Module: `headspace.forge.apply`
Returns: `dict[str, bool]`

Health check for required components:

    {
      "headroom":               true,
      "headroom_superinstance": true,
      "ternary_gc_advisor":     true,
      "baton_system":           true,
      "gc_ledger":              true
    }

### `headspace.forge.context.forge_snapshot()`

Module: `headspace.forge.context`
Returns: `dict`

Current state snapshot. Useful at cold start:

    {
      "ts":             "2026-06-14T01:55:00Z",
      "app":            "headspace",
      "version":        "0.2.0",
      "proxy":          "running",   // or "down"
      "swarm":          "running",   // or "down"
      "extension":      "v0.1.0",
      "baton_bottles":  5,
      "ledger_entries": 51
    }

## Environment variables

  HEADSPACE_HOME         default ~/.headspace                 (CLI state, pid files)
  HEADSPACE_WORKSPACE    default ~/.openclaw/workspace        (data dir)
  HEADSPACE_SWARM_PORT   default 8765 in server.py, 18000 in CLI
  HEADROOM_BIN           default ~/.local/bin/headroom or $PATH
  WORKSPACE              same as HEADSPACE_WORKSPACE, for proxy
  BATON_DIR              default $HEADSPACE_WORKSPACE/baton-system

## Error and degradation table

  swarm_unavailable      -> /policy returns balanced default
                            x-headspace-swarm header omitted
  advisor_unavailable    -> /status returns {"status":"advisor_unavailable",...}
  ledger_empty           -> x-headspace-gc is "<<GC ledger: empty>>"
  baton_dir_missing      -> x-headspace-baton is "<<BATON: no fleet bottles>>"
                            fleet_context() returns "<<BATON: no fleet bottles>>"

## Quick reference card

  Swarm:    GET  http://127.0.0.1:18000/api/v1/policy
            GET  http://127.0.0.1:18000/api/v1/advise
            GET  http://127.0.0.1:18000/api/v1/status
            POST http://127.0.0.1:18000/api/v1/train
            GET  http://127.0.0.1:18000/healthz

  Proxy:    GET  http://127.0.0.1:8788/livez
            [any LLM call]  -> reads x-headspace-{gc,swarm,baton} on response

  Python:   from headspace import compress_for_prompt
            from headspace.baton.bridge import fleet_context, sync, commit
            from headspace.forge.context import forge_snapshot
            from headspace.forge.apply import check_components

  Headers:  x-headspace        version
            x-headspace-gc     GC ledger
            x-headspace-swarm  PID state
            x-headspace-baton  fleet bottles
