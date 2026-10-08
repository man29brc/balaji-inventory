"""Offline tests: python -m unittest router/test_router.py  (no network, no API key)."""
import json
import tempfile
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import router as R

CFG = R.load_config()


def req(text, model="router/auto"):
    return {"model": model, "messages": [{"role": "user", "content": text}]}


class Classify(unittest.TestCase):
    def tier(self, text, model="router/auto"):
        return R.classify(req(text)["messages"], model, CFG)[0]

    def test_simple_writing(self):
        self.assertEqual(self.tier("Write a caption for my home loan reel"), "simple")
        self.assertEqual(self.tier("Translate this to Gujarati"), "simple")

    def test_standard_analysis(self):
        self.assertEqual(self.tier("Make a 90 day plan for CSC Balaji"), "standard")
        self.assertEqual(self.tier("hello there"), "standard")

    def test_compliance_goes_hard(self):
        self.assertEqual(self.tier("Write a caption about SIP returns"), "hard")
        self.assertEqual(self.tier("term plan hook for my reel"), "hard")

    def test_keyword_needs_word_boundary(self):
        self.assertNotEqual(self.tier("write a caption about a sipping cafe"), "hard")

    def test_sensitive_wins_over_everything(self):
        self.assertEqual(self.tier("caption for client ABCDE1234F"), "sensitive")
        self.assertEqual(self.tier("call 9876543210 about SIP"), "sensitive")
        self.assertEqual(self.tier("Aadhaar 1234 5678 9012", "router/simple"), "sensitive")

    def test_forced_tier(self):
        self.assertEqual(self.tier("plan my week", "router/simple"), "simple")
        self.assertEqual(self.tier("caption about SIP", "router/standard"), "standard")


class Effort(unittest.TestCase):
    def test_clamp(self):
        self.assertEqual(R.clamp_effort("low", ["xhigh", "high"]), "high")
        self.assertEqual(R.clamp_effort("medium", ["max", "high", "low"]), "high")  # tie -> higher
        self.assertEqual(R.clamp_effort("high", ["high", "medium", "low"]), "high")
        self.assertEqual(R.clamp_effort("high", []), None)
        self.assertEqual(R.clamp_effort("high", None), "high")


class Decide(unittest.TestCase):
    def setUp(self):
        self.info = R.ModelInfo(CFG)
        self.tmp = tempfile.TemporaryDirectory()
        self.spend = R.Spend(CFG, Path(self.tmp.name) / "s.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_simple_request_shape(self):
        out, d = R.decide(req("write a caption"), CFG, self.info)
        self.assertEqual(out["models"], ["z-ai/glm-5.3-flash", "google/gemini-3.1-flash-lite"])
        self.assertNotIn("model", out)
        self.assertEqual(out["reasoning"], {"effort": "low"})
        self.assertEqual(out["provider"]["data_collection"], "deny")

    def test_standard_high_effort_chinese_primary_gemini_fallback(self):
        out, d = R.decide(req("compare two loan plans"), CFG, self.info)
        self.assertEqual(out["models"][0], "deepseek/deepseek-v4.1-flash")
        self.assertEqual(out["models"][1].split("/")[0], "google")
        self.assertEqual(out["reasoning"]["effort"], "high")

    def test_sensitive_requires_zdr_and_ignores_client_provider(self):
        body = req("PAN ABCDE1234F summary")
        body["provider"] = {"zdr": False, "order": ["x"]}
        out, d = R.decide(body, CFG, self.info)
        self.assertTrue(out["provider"]["zdr"])
        self.assertEqual(out["provider"]["order"], ["x"])
        self.assertEqual(d["tier"], "sensitive")

    def test_client_max_tokens_respected_when_lower(self):
        body = req("write a caption")
        body["max_tokens"] = 200
        self.assertEqual(R.decide(body, CFG, self.info)[0]["max_tokens"], 200)
        body["max_tokens"] = 999999
        self.assertEqual(R.decide(body, CFG, self.info)[0]["max_tokens"], 3000)

    def test_client_reasoning_not_overridden(self):
        body = req("write a caption")
        body["reasoning"] = {"max_tokens": 2000}
        self.assertEqual(R.decide(body, CFG, self.info)[0]["reasoning"], {"max_tokens": 2000})

    def test_budget_downgrade_and_block(self):
        cfg = json.loads(json.dumps(CFG))
        cfg["budget"].update(daily_usd=1.0, monthly_usd=100.0)
        spend = R.Spend(cfg, Path(self.tmp.name) / "b.json")
        spend.add(0.85)
        self.assertEqual(spend.status(), "soft")
        _, d = R.decide(req("compare two loan plans"), cfg, self.info, spend)
        self.assertEqual(d["tier"], "simple")
        _, d = R.decide(req("caption about SIP"), cfg, self.info, spend)
        self.assertEqual(d["tier"], "hard")  # compliance tier is never downgraded
        spend.add(0.2)
        with self.assertRaises(R.BudgetExceeded):
            R.decide(req("anything"), cfg, self.info, spend)


class Cost(unittest.TestCase):
    def test_reported_cost_preferred_then_estimate(self):
        info = R.ModelInfo(CFG)
        self.assertEqual(R.cost_of({"cost": 0.5, "prompt_tokens": 1}, "z-ai/glm-5.3-flash", info), 0.5)
        est = R.cost_of({"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000}, "z-ai/glm-5.3-flash", info)
        self.assertAlmostEqual(est, 0.65)
        self.assertEqual(R.cost_of(None, "x", info), 0.0)


class FakeUpstream(BaseHTTPRequestHandler):
    seen = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeUpstream.seen.append(body)
        model = body.get("model") or body["models"][0]
        usage = {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.01}
        if body.get("stream"):
            self.send_response(200)
            self.end_headers()
            for chunk in ({"model": model, "choices": [{"delta": {"content": "hi"}}]},
                          {"model": model, "choices": [], "usage": usage}):
                self.wfile.write(b"data: " + json.dumps(chunk).encode() + b"\n\n")
            self.wfile.write(b"data: [DONE]\n\n")
            return
        out = json.dumps({"model": model, "choices": [{"message": {"content": "hi"}}], "usage": usage}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


class EndToEnd(unittest.TestCase):
    def test_proxy_routes_and_tracks_spend(self):
        up = ThreadingHTTPServer(("127.0.0.1", 0), FakeUpstream)
        threading.Thread(target=up.serve_forever, daemon=True).start()
        old = R.OPENROUTER
        R.OPENROUTER = "http://127.0.0.1:%d" % up.server_port
        tmp = tempfile.TemporaryDirectory()
        R.Handler.cfg, R.Handler.api_key, R.Handler.token = CFG, "test-key", ""
        R.Handler.info = R.ModelInfo(CFG)
        R.Handler.info.fetched = 1e18  # skip live fetch
        R.Handler.spend = R.Spend(CFG, Path(tmp.name) / "s.json")
        srv = ThreadingHTTPServer(("127.0.0.1", 0), R.Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            r = urllib.request.Request("http://127.0.0.1:%d/v1/chat/completions" % srv.server_port,
                                       data=json.dumps(req("write a caption")).encode(),
                                       headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(r) as resp:
                data = json.load(resp)
                self.assertEqual(resp.headers["X-Router-Tier"], "simple")
            self.assertEqual(data["x_router"]["effort"], "low")
            self.assertEqual(FakeUpstream.seen[-1]["reasoning"], {"effort": "low"})
            self.assertAlmostEqual(R.Handler.spend.totals()[1], 0.01)

            body = req("write a caption")
            body["stream"] = True
            r = urllib.request.Request("http://127.0.0.1:%d/v1/chat/completions" % srv.server_port,
                                       data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(r) as resp:
                raw = resp.read()
            self.assertIn(b"[DONE]", raw)
            self.assertAlmostEqual(R.Handler.spend.totals()[1], 0.02)  # streamed usage was billed too
        finally:
            srv.shutdown()
            srv.server_close()
            up.shutdown()
            up.server_close()
            R.OPENROUTER = old
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
