# Agent Patterns

How an agent can choose to integrate with headspace. There are three
patterns, in order of increasing coupling. Pick the one that matches
how much you want to know about the fleet.

## The Thin Agent

The minimum viable integration. You do not know headspace exists.

  - Knows nothing about fleet state
  - Sends LLM requests through the headroom proxy (or does not, it does
    not matter for the headspace side)
  - If the proxy is in the path, headspace injects `x-headspace-*`
    headers on the response; the agent can ignore them
  - Compression happens automatically inside the proxy
  - No code changes required on the agent side

When to use this pattern: you are a one-off agent, an experimental
prompt, a smoke test, or you do not want to take a dependency on
headspace internals.

What you get: free context compression, free fleet state in response
headers (if you happen to read them), no fleet awareness.

What you do not get: targeted compression, fleet coordination, the
ability to push bottles to other agents.

## The Aware Agent

Reads the swarm and the fleet, but does not write back.

  - Calls the swarm API at startup to load the current policy
  - Calls `fleet_context()` (or reads `x-headspace-baton` from the
    proxy response) to know what other agents are doing
  - Adjusts its own behavior (prompt size, model choice, retry policy)
    based on the compression profile it loaded
  - Does not push bottles into the hot tier
  - Does not call `POST /api/v1/train`

When to use this pattern: you are a long-running agent that wants to
be a good citizen. You want to know "is the fleet under pressure?" and
"what did the other agents find recently?" but you do not have
anything to contribute to the fleet.

What you get: dynamic compression, fleet awareness, prompt that
includes fleet state.

What you do not get: the ability to nudge the swarm, the ability to
share findings with other agents.

Pseudocode:

    from headspace.baton.bridge import fleet_context
    import urllib.request, json

    def startup():
        policy = json.loads(urllib.request.urlopen(
            "http://127.0.0.1:18000/api/v1/policy"
        ).read())
        fleet  = fleet_context()
        return policy, fleet

    def make_prompt(user_msg, policy, fleet):
        setpoint = policy["setpoint_pct"]
        system = (
            f"You run in headspace, profile={policy['profile']} "
            f"setpoint={setpoint}%.\n"
            f"Fleet state:\n{fleet}\n"
        )
        return [
            {"role":"system","content":system},
            {"role":"user","content":user_msg},
        ]

## The Active Agent

Full read/write participant in the headspace plane.

  - Everything the Aware Agent does, plus:
  - Pushes bottles to `baton-system/tiers/hot/` via `commit()`
  - Calls `POST /api/v1/train` when it has new evidence the current
    policy is wrong (e.g. it just observed a disk spike)
  - Reads `x-headspace-swarm` on every LLM response and uses it as a
    signal in its own policy loop
  - May run its own swarm server (port 18000) or share one with the
    rest of the fleet

When to use this pattern: you are a primary agent in the fleet, you
generate non-trivial artifacts that other agents need, and you have
authority to influence the swarm.

What you get: full participation. Your findings propagate to other
agents, your evidence feeds the swarm, the swarm's vote affects
compression across the fleet.

What you take on: you are now part of the feedback loop. If you push
garbage bottles, the swarm converges on garbage. If you push good
evidence, the swarm converges faster.

Pseudocode:

    from headspace.baton.bridge import commit
    import urllib.request, json

    def share_finding(name, body):
        commit(
            filename=f"{name}-{int(time.time())}.md",
            content=(
                f"**Source:** {name}\n"
                f"**Date:**   {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n\n"
                f"{body}\n"
            ),
        )

    def push_evidence(entries):
        req = urllib.request.Request(
            "http://127.0.0.1:18000/api/v1/train",
            data=json.dumps({"entries": entries}).encode(),
            headers={"Content-Type":"application/json"},
        )
        return json.loads(urllib.request.urlopen(req).read())

## Choosing a pattern

  - I am a one-shot tool         -> Thin
  - I run in a loop and read     -> Aware
  - I run in a loop and write    -> Active

You can upgrade in place. A Thin agent that suddenly needs fleet
context can become Aware by adding two lines at startup. An Aware
agent that finds something worth sharing can call `commit()` and
become Active.

## What headspace does not do (yet)

To set expectations:

  - It does not choose your model. The policy affects how aggressively
    you compress; it does not pick the model.
  - It does not arbitrate agent priority. If two Active agents push
    conflicting bottles, both land in the hot tier and the most recent
    wins (LIFO).
  - It does not authenticate. Both the proxy and the swarm are bound
    to loopback by default. Do not expose them.
  - It does not encrypt. Bottles are plaintext markdown. Do not put
    secrets in them.
