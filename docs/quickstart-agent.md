# Quickstart: From first request to optimized context

You are an agent. You have five minutes. You want to use headspace.
Here is the path.

## Step 1: Ask the swarm what compression profile to use

    curl -s http://127.0.0.1:18000/api/v1/policy

You should get back something like:

    {
      "profile":        "aggressive",
      "setpoint_pct":   10,
      "deadband":       0.5,
      "aggression_cap": 2.5
    }

If you get a connection error, the swarm is not running. Fall back to
balanced locally (`setpoint_pct: 20, deadband: 1.0`). Carry on.

In Python:

    import urllib.request, json

    def policy():
        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:18000/api/v1/policy", timeout=2
            ) as r:
                return json.loads(r.read())
        except Exception:
            return {"profile":"balanced","setpoint_pct":20,
                    "deadband":1.0,"aggression_cap":5.0}

    p = policy()
    # -> {"profile":"aggressive","setpoint_pct":10,"deadband":0.5,
    #     "aggression_cap":2.5}

## Step 2: Get fleet context

    from headspace.baton.bridge import fleet_context
    fleet = fleet_context()

    # -> "<<BATON:\n  cocapn-training: ...\n  gc-intelligence: ...\n  ...\n>>"

Or from curl, just read the `x-headspace-baton` response header from
any call through the headroom proxy (see step 4).

## Step 3: Check that the swarm is actually converged

    curl -s http://127.0.0.1:18000/api/v1/status

Look for `"status": "ok"`. If you see `"insufficient_data"`, you need
more ledger entries before the swarm has a meaningful vote. The
current live state in the SuperInstance fleet is `ok` with 51 ledger
entries and a fitness of 6.188.

## Step 4: Compress your own context to the setpoint

Take the `setpoint_pct` from step 1 and trim your context to that
fraction of its current size. Example policy: if setpoint is 10, keep
roughly 10% of your prior turns and tool outputs (the most recent and
most important ones; you choose).

If you do not want to roll your own compression, route the LLM call
through the headroom proxy. The proxy will inject fleet context for you.

## Step 5: Send the call through the headroom proxy

The headroom proxy sits at `http://127.0.0.1:8788`. Point your OpenAI-
compatible client at it instead of the real LLM endpoint.

    # Plain curl
    curl -X POST http://127.0.0.1:8788/v1/chat/completions \
      -H "Content-Type: application/json" \
      -d '{
        "model": "gpt-4o-mini",
        "messages": [
          {"role":"system","content":"You are a SuperInstance agent."},
          {"role":"user","content":"Summarize the current fleet state."}
        ]
      }'

    # OpenAI Python client
    from openai import OpenAI
    client = OpenAI(base_url="http://127.0.0.1:8788/v1", api_key="not-needed")
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role":"user","content":"Summarize fleet state."}],
    )
    print(resp.choices[0].message.content)

    # Inspect the injected headers
    # In curl:  curl -i ...
    # In Python:
    import httpx
    r = httpx.post("http://127.0.0.1:8788/v1/chat/completions", json={...})
    print(r.headers.get("x-headspace-gc"))
    print(r.headers.get("x-headspace-swarm"))
    print(r.headers.get("x-headspace-baton"))
    print(r.headers.get("x-headspace"))  # version

## Full 30-line Python agent

If you just want a copy-paste starting point:

    #!/usr/bin/env python3
    """Minimal headspace-aware agent."""
    import json, urllib.request

    SWARM = "http://127.0.0.1:18000"
    PROXY = "http://127.0.0.1:8788"

    def get_json(url):
        with urllib.request.urlopen(url, timeout=2) as r:
            return json.loads(r.read())

    def get_policy():
        try:
            return get_json(f"{SWARM}/api/v1/policy")
        except Exception:
            return {"profile":"balanced","setpoint_pct":20,
                    "deadband":1.0,"aggression_cap":5.0}

    def get_fleet_ctx():
        try:
            from headspace.baton.bridge import fleet_context
            return fleet_context()
        except Exception:
            return "<<BATON: no fleet bottles>>"

    def call_llm(messages):
        body = json.dumps({
            "model": "gpt-4o-mini",
            "messages": messages,
        }).encode()
        req = urllib.request.Request(
            f"{PROXY}/v1/chat/completions",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return {
                "headers": {k: r.headers[k] for k in r.headers
                            if k.lower().startswith("x-headspace")},
                "body": json.loads(r.read()),
            }

    if __name__ == "__main__":
        p = get_policy()
        fleet = get_fleet_ctx()
        sys = f"You run in headspace. Policy: {p['profile']} "\
              f"(setpoint {p['setpoint_pct']}%).\nFleet:\n{fleet}"
        result = call_llm([
            {"role":"system","content":sys},
            {"role":"user","content":"What should I be working on?"},
        ])
        print("LLM:", result["body"]["choices"][0]["message"]["content"])
        print("Headers:", json.dumps(result["headers"], indent=2))

## What good looks like

After the five steps, in the SuperInstance fleet, you should see:

  - `x-headspace-gc`:    `<<GC ledger:51 sampled:51 disk:88% freed:1498512kb ...>>`
  - `x-headspace-swarm`: `<<SWARM kp:10.0 ki:1.0 kd:0.1>>`
  - `x-headspace-baton`: `<<BATON:\n  cocapn-training: ...\n  ...\n>>`
  - `x-headspace`:       `0.2.0`

Those four lines tell you: GC is running, swarm is converged (kp/ki/kd
are real values, not zeros), 5 bottles are in flight, and you are on
v0.2.0. If any of those is missing, see the failure modes in
`for-agents.md` section 8.

## Next

  - `for-agents.md`        full agent guide
  - `api-reference.md`     every endpoint, header, and Python function
  - `../agents/README.md`  integration patterns (Thin / Aware / Active agent)
  - `../SYSTEM.md`         cold-start state for any new agent
