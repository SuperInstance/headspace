"""Unit tests for the HeadspaceAgent SDK.

These tests do NOT require a running headspace swarm server - they exercise
the SDK with a deliberately-unreachable swarm URL and verify graceful
fallback, plus the local-only logic (compression, fleet strings, prompts,
lifecycle).
"""

import json
import os
import time
import unittest
from pathlib import Path
from unittest import mock

from headspace.agent import (
    DEFAULT_SWARM_URL,
    DEFAULT_WORKSPACE,
    FleetContext,
    HeadspaceAgent,
    SwarmPolicy,
    compress,
    fleet_state,
    policy,
)


# A swarm URL guaranteed to be unreachable on any sane host.
OFFLINE_URL = "http://127.0.0.1:1"


class TestSwarmPolicy(unittest.TestCase):
    def test_defaults(self):
        p = SwarmPolicy()
        self.assertEqual(p.profile, "balanced")
        self.assertEqual(p.setpoint_pct, 20)
        self.assertEqual(p.deadband, 1.0)
        self.assertEqual(p.aggression_cap, 2.0)
        self.assertEqual(p.integral_limit, 20.0)
        self.assertEqual(p.fitness, 0.0)

    def test_fresh_policy_not_stale(self):
        p = SwarmPolicy(fetched_at=time.time())
        self.assertFalse(p.is_stale)

    def test_old_policy_is_stale(self):
        p = SwarmPolicy(fetched_at=time.time() - 7200)
        self.assertTrue(p.is_stale)

    def test_age_seconds(self):
        p = SwarmPolicy(fetched_at=time.time() - 100)
        self.assertGreaterEqual(p.age_seconds, 99.0)
        self.assertLessEqual(p.age_seconds, 101.0)


class TestFleetContext(unittest.TestCase):
    def test_defaults(self):
        f = FleetContext()
        self.assertEqual(f.bottles, [])
        self.assertEqual(f.gc_ledger_summary, "")
        self.assertEqual(f.disk_gb_total, 0.0)
        self.assertEqual(f.disk_gb_free, 0.0)
        self.assertEqual(f.disk_pct_used, 0.0)

    def test_bottles_default_factory_is_independent(self):
        # Each instance should get its own list (mutable default trap guard).
        a = FleetContext()
        b = FleetContext()
        a.bottles.append("x")
        self.assertEqual(b.bottles, [])


class TestHeadspaceAgentInit(unittest.TestCase):
    def test_init_with_offline_swarm_uses_defaults(self):
        agent = HeadspaceAgent(
            "test-agent-1",
            swarm_url=OFFLINE_URL,
            workspace=Path("/tmp"),
        )
        # sync_policy should have fallen back to defaults
        self.assertIsNotNone(agent._policy)
        self.assertEqual(agent._policy.profile, "balanced")
        self.assertIsNotNone(agent._fleet)
        self.assertEqual(agent.agent_id, "test-agent-1")

    def test_init_strips_trailing_slash(self):
        agent = HeadspaceAgent("a", swarm_url="http://example.com/", workspace=Path("/tmp"))
        self.assertEqual(agent.swarm_url, "http://example.com")

    def test_uptime_increases(self):
        agent = HeadspaceAgent("a", swarm_url=OFFLINE_URL, workspace=Path("/tmp"))
        t1 = agent.uptime
        time.sleep(0.05)
        t2 = agent.uptime
        self.assertGreater(t2, t1)

    def test_repr_is_ascii_safe(self):
        agent = HeadspaceAgent("a", swarm_url=OFFLINE_URL, workspace=Path("/tmp"))
        r = repr(agent)
        r.encode("ascii")  # should not raise
        self.assertIn("a", r)
        self.assertIn("HeadspaceAgent", r)


class TestCompress(unittest.TestCase):
    def test_balanced_dedups_exact_lines(self):
        text = "alpha\nbeta\nalpha\n\nbeta\ngamma"
        out = compress(text, profile="balanced")
        self.assertEqual(out, "alpha\nbeta\ngamma")

    def test_aggressive_drops_comments(self):
        text = "# this is a comment\nkeep this\n# important: keep this comment"
        out = compress(text, profile="aggressive")
        self.assertIn("keep this", out)
        self.assertNotIn("this is a comment", out)
        self.assertIn("important: keep this comment", out)

    def test_aggressive_truncates_long_system_prompts(self):
        long_prompt = "you are " + ("x" * 300)
        out = compress(long_prompt, profile="aggressive")
        self.assertIn("[truncated]", out)
        self.assertLess(len(out), len(long_prompt))

    def test_conservative_caps_long_lines(self):
        long_line = "y" * 600
        out = compress(long_line, profile="conservative")
        self.assertIn("[+truncated]", out)
        self.assertLessEqual(len(out), 500)

    def test_empty_returns_empty(self):
        self.assertEqual(compress("", profile="aggressive"), "")

    def test_unknown_profile_falls_back_to_balanced(self):
        text = "x\nx\ny"
        out = compress(text, profile="weird-profile")
        # Balanced behavior: dedup
        self.assertEqual(out, "x\ny")


class TestFleetString(unittest.TestCase):
    def test_fleet_string_contains_disk_tag(self):
        agent = HeadspaceAgent("a", swarm_url=OFFLINE_URL, workspace=Path("/tmp"))
        s = agent.fleet_string()
        self.assertIn("<<FLT d:", s)
        self.assertIn("%", s)
        self.assertIn("G>>", s)

    def test_fleet_string_includes_bottles_when_present(self):
        # Make a fake workspace with hot bottles
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            hot = tmp / "baton-system" / "tiers" / "hot"
            hot.mkdir(parents=True, exist_ok=True)
            (hot / "z-2025-01-01.md").write_text("a")
            (hot / "a-2025-02-01.md").write_text("b")
            (hot / "m-2025-03-01.md").write_text("c")
            agent = HeadspaceAgent(
                "a", swarm_url=OFFLINE_URL, workspace=tmp
            )
            agent.sync_fleet()
            s = agent.fleet_string()
            self.assertIn("<<BAT 3 btl>>", s)
            # bottles list is reverse-sorted by stem
            self.assertEqual(agent.fleet.bottles[:3],
                             ["z-2025-01-01", "m-2025-03-01", "a-2025-02-01"])


class TestBuildPrompt(unittest.TestCase):
    def test_build_prompt_contains_fleet_tag(self):
        agent = HeadspaceAgent("a", swarm_url=OFFLINE_URL, workspace=Path("/tmp"))
        out = agent.build_prompt("You are helpful.", "Hello")
        self.assertIn("<FLT>", out)
        self.assertIn("</FLT>", out)
        self.assertIn("You are helpful.", out)
        self.assertIn("Hello", out)

    def test_build_prompt_applies_compression(self):
        agent = HeadspaceAgent("a", swarm_url=OFFLINE_URL, workspace=Path("/tmp"))
        # Force aggressive profile
        agent._policy = SwarmPolicy(profile="aggressive", fetched_at=time.time())
        long_comment = "# " + ("filler " * 50)
        sys_prompt = long_comment + "\nYou are a helpful assistant."
        out = agent.build_prompt(sys_prompt, "Hi")
        # The filler comment should be dropped
        self.assertNotIn("filler", out)
        self.assertIn("You are a helpful assistant.", out)

    def test_build_prompt_is_ascii_safe(self):
        agent = HeadspaceAgent("a", swarm_url=OFFLINE_URL, workspace=Path("/tmp"))
        out = agent.build_prompt("system", "user")
        out.encode("ascii")  # should not raise


class TestTick(unittest.TestCase):
    def test_tick_calls_on_tick(self):
        captured = {}

        class MyAgent(HeadspaceAgent):
            def on_tick(self, context, fleet):
                captured["context"] = context
                captured["fleet"] = fleet
                captured["ticks"] = self._tick_count
                return "act"

        a = MyAgent("a", swarm_url=OFFLINE_URL, workspace=Path("/tmp"))
        action = a.tick()
        self.assertEqual(action, "act")
        self.assertIn("context", captured)
        self.assertIn("fleet", captured)
        self.assertEqual(captured["ticks"], 1)

    def test_tick_returns_none_by_default(self):
        a = HeadspaceAgent("a", swarm_url=OFFLINE_URL, workspace=Path("/tmp"))
        self.assertIsNone(a.tick())

    def test_tick_swallows_exceptions(self):
        class BadAgent(HeadspaceAgent):
            def on_tick(self, context, fleet):
                raise RuntimeError("boom")

        a = BadAgent("a", swarm_url=OFFLINE_URL, workspace=Path("/tmp"))
        self.assertIsNone(a.tick())  # should not raise

    def test_tick_auto_syncs_when_stale(self):
        a = HeadspaceAgent(
            "a",
            swarm_url=OFFLINE_URL,
            workspace=Path("/tmp"),
            auto_sync_interval=0,  # always resync
        )
        # Each tick should re-sync policy and fleet
        with mock.patch.object(a, "sync_policy") as sp, mock.patch.object(a, "sync_fleet") as sf:
            a.tick()
            self.assertTrue(sp.called)
            self.assertTrue(sf.called)


class TestConvenienceFunctions(unittest.TestCase):
    def test_fleet_state_returns_string(self):
        s = fleet_state(OFFLINE_URL)
        self.assertIsInstance(s, str)
        self.assertIn("<<FLT", s)

    def test_compress_function(self):
        s = compress("a\nb\na", profile="balanced")
        self.assertEqual(s, "a\nb")

    def test_policy_function(self):
        p = policy(OFFLINE_URL)
        self.assertIsInstance(p, dict)
        self.assertIn("profile", p)
        self.assertIn("setpoint_pct", p)
        self.assertIn("deadband", p)
        self.assertIn("aggression_cap", p)
        self.assertIn("fitness", p)
        self.assertIn("stale", p)


class TestNoServerNoCrash(unittest.TestCase):
    """Sanity: nothing in the SDK requires a live server."""

    def test_init_doesnt_raise(self):
        HeadspaceAgent("x", swarm_url=OFFLINE_URL, workspace=Path("/tmp"))

    def test_tick_doesnt_raise(self):
        a = HeadspaceAgent("x", swarm_url=OFFLINE_URL, workspace=Path("/tmp"))
        for _ in range(3):
            a.tick()

    def test_fleet_string_doesnt_raise(self):
        a = HeadspaceAgent("x", swarm_url=OFFLINE_URL, workspace=Path("/tmp"))
        a.fleet_string()

    def test_build_prompt_doesnt_raise(self):
        a = HeadspaceAgent("x", swarm_url=OFFLINE_URL, workspace=Path("/tmp"))
        a.build_prompt("sys", "user")


if __name__ == "__main__":
    unittest.main(verbosity=2)
