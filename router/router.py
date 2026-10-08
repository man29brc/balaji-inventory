#!/usr/bin/env python3
"""Query router for OpenRouter: picks model + reasoning effort per query and enforces a budget.

Runs as an OpenAI-compatible endpoint (point TypingMind's custom model at it).
Standard library only. Needs OPENROUTER_API_KEY in the environment to serve.

  python router.py --dry-run "write a caption for my loan reel"   # no key, no network spend
  python router.py --check                                        # verify slugs/efforts vs live list
  python router.py --serve                                        # start on 127.0.0.1:8787

Virtual models you can pick in the chat app:
  router/auto  classify each query (default)      router/simple    router/standard
  router/hard  strong model, compliance work      router/sensitive zero-data-retention only
"""
import argparse
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
OPENROUTER = "https://openrouter.ai/api/v1"
LADDER = ["none", "minimal", "low", "medium", "high", "xhigh", "max"]
TIERS = ("simple", "standard", "hard", "sensitive")

SENSITIVE_PATTERNS = {
    "PAN": re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"),
    "Aadhaar": re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b"),
    "phone": re.compile(r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{9}(?!\d)"),
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
}


def load_config(path=None):
    path = Path(path or os.environ.get("ROUTER_CONFIG") or HERE / "config.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------- classify

def message_text(messages):
    """Return (last_user_text, all_text) from OpenAI-style messages, ignoring image parts."""
    def flat(content):
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return " ".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text")
        return ""
    last_user = ""
    parts = []
    for m in messages or []:
        text = flat(m.get("content"))
        parts.append(text)
        if m.get("role") == "user":
            last_user = text
    return last_user, "\n".join(parts)


def _has_word(text, words):
    low = text.lower()
    return [w for w in words if re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", low)]


def find_sensitive(text):
    return [name for name, rx in SENSITIVE_PATTERNS.items() if rx.search(text)]


def classify(messages, requested_model, cfg):
    """Return (tier, reason). Sensitive data always wins, even over a forced tier."""
    last_user, all_text = message_text(messages)
    found = find_sensitive(all_text)
    if found:
        return "sensitive", "contains " + "/".join(found)

    forced = requested_model.split("/", 1)[1] if requested_model.startswith("router/") else ""
    if forced in TIERS:
        return forced, "forced by model name"

    rules = cfg["rules"]
    hits = _has_word(all_text, rules["compliance_words"])
    if hits:
        return "hard", "compliance keyword: " + hits[0]
    if _has_word(last_user, rules["standard_words"]) or len(all_text) > rules["simple_max_chars"] * 2:
        return "standard", "analysis keyword or long context"
    if len(last_user) <= rules["simple_max_chars"] and _has_word(last_user, rules["simple_words"]):
        return "simple", "short writing task"
    return "standard", "default"


# --------------------------------------------------------------------------- effort

def clamp_effort(desired, supported):
    """Nearest supported effort to `desired`. supported=None -> any value allowed; [] -> no reasoning."""
    if supported is None:
        return desired
    ladder = [e for e in supported if e in LADDER]
    if not ladder:
        return None
    want = LADDER.index(desired)
    return min(ladder, key=lambda e: (abs(LADDER.index(e) - want), -LADDER.index(e)))


class ModelInfo:
    """Effort lists and prices: config snapshot, overridden by the live OpenRouter list when reachable."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.live = {}
        self.fetched = 0.0
        self.lock = threading.Lock()

    def refresh(self, force=False):
        with self.lock:
            if not force and time.time() - self.fetched < 3600:
                return bool(self.live)
            try:
                req = urllib.request.Request(OPENROUTER + "/models")
                with urllib.request.urlopen(req, timeout=20) as r:
                    data = json.load(r)["data"]
                self.live = {m["id"]: m for m in data}
                self.fetched = time.time()
                return True
            except Exception as e:  # network trouble must not stop routing
                print("[router] live model list unavailable, using config snapshot:", e, file=sys.stderr)
                self.fetched = time.time() - 3000  # retry in ~10 minutes
                return False

    def efforts(self, slug):
        live = self.live.get(slug)
        if live is not None:
            r = live.get("reasoning")
            if not r:
                return []
            return r.get("supported_efforts")  # None means any value accepted
        return self.cfg["models"].get(slug, {}).get("efforts")

    def price(self, slug):
        """(input, output) USD per million tokens, or None."""
        live = self.live.get(slug)
        if live is not None:
            p = live.get("pricing", {})
            try:
                return float(p["prompt"]) * 1e6, float(p["completion"]) * 1e6
            except (KeyError, TypeError, ValueError):
                pass
        p = self.cfg["models"].get(slug, {}).get("price")
        return tuple(p) if p else None


# --------------------------------------------------------------------------- budget

class Spend:
    """Per-day and per-month spend in USD, persisted to spend.json (IST by default)."""

    def __init__(self, cfg, path=None):
        self.cfg = cfg["budget"]
        self.path = Path(path or os.environ.get("ROUTER_SPEND_FILE") or HERE / "spend.json")
        self.lock = threading.Lock()
        try:
            self.data = json.loads(self.path.read_text())
        except Exception:
            self.data = {}

    def _keys(self):
        tz = timezone(timedelta(hours=self.cfg.get("timezone_offset_hours", 5.5)))
        now = datetime.now(tz)
        return now.strftime("%Y-%m-%d"), now.strftime("%Y-%m")

    def totals(self):
        day, month = self._keys()
        return self.data.get("d:" + day, 0.0), self.data.get("m:" + month, 0.0)

    def status(self):
        """'ok', 'soft' (over soft limit) or 'blocked'."""
        day, month = self.totals()
        dcap, mcap = self.cfg["daily_usd"], self.cfg["monthly_usd"]
        if day >= dcap or month >= mcap:
            return "blocked"
        soft = self.cfg.get("soft_limit_pct", 80) / 100
        if day >= dcap * soft or month >= mcap * soft:
            return "soft"
        return "ok"

    def add(self, usd):
        if usd <= 0:
            return
        with self.lock:
            day, month = self._keys()
            self.data["d:" + day] = self.data.get("d:" + day, 0.0) + usd
            self.data["m:" + month] = self.data.get("m:" + month, 0.0) + usd
            try:
                self.path.write_text(json.dumps(self.data, indent=1))
            except OSError as e:
                print("[router] could not save spend file:", e, file=sys.stderr)


# --------------------------------------------------------------------------- request building

def decide(body, cfg, info, spend=None):
    """Route one chat request. Returns (upstream_body, decision_dict)."""
    requested = body.get("model", "router/auto")
    tier, reason = classify(body.get("messages"), requested, cfg)

    status = spend.status() if spend else "ok"
    if status == "blocked":
        raise BudgetExceeded(spend.totals())
    if status == "soft" and "downgrade_to" in cfg["tiers"][tier]:
        tier, reason = cfg["tiers"][tier]["downgrade_to"], reason + " | downgraded: near budget"

    t = cfg["tiers"][tier]
    models = t["models"]
    out = {k: v for k, v in body.items() if k != "model"}
    if len(models) > 1:
        out["models"] = models
    else:
        out["model"] = models[0]

    effort = clamp_effort(t["effort"], info.efforts(models[0]))
    if effort and "reasoning" not in out:
        out["reasoning"] = {"effort": effort}

    cap = t["max_tokens"]
    asked = body.get("max_tokens") or body.get("max_completion_tokens")
    out["max_tokens"] = min(asked, cap) if asked else cap
    out.pop("max_completion_tokens", None)

    if t.get("provider"):
        out["provider"] = {**(body.get("provider") or {}), **t["provider"]}  # tier privacy rules win

    return out, {"tier": tier, "reason": reason, "models": models, "effort": effort,
                 "max_tokens": out["max_tokens"], "provider": out.get("provider"), "budget": status}


class BudgetExceeded(Exception):
    pass


def cost_of(usage, model, info):
    """Prefer OpenRouter's reported cost; otherwise estimate from token counts and price."""
    if not usage:
        return 0.0
    if isinstance(usage.get("cost"), (int, float)):
        return float(usage["cost"])
    price = info.price(model) if model else None
    if not price:
        return 0.0
    return (usage.get("prompt_tokens", 0) * price[0] + usage.get("completion_tokens", 0) * price[1]) / 1e6


# --------------------------------------------------------------------------- server

class Handler(BaseHTTPRequestHandler):
    cfg = info = spend = None
    api_key = ""
    token = ""

    def log_message(self, *a):  # keep prompts out of logs; we log decisions ourselves
        pass

    def _send_json(self, code, obj, extra=None):
        raw = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self._cors()
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "authorization, content-type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Expose-Headers", "x-router-tier, x-router-effort, x-router-reason")

    def _authorized(self):
        return not self.token or self.headers.get("Authorization", "") == "Bearer " + self.token

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if not self._authorized():
            return self._send_json(401, {"error": {"message": "bad router token"}})
        if self.path.rstrip("/") in ("/v1/models", "/models"):
            ids = ["router/auto"] + ["router/" + t for t in TIERS]
            return self._send_json(200, {"object": "list", "data": [{"id": i, "object": "model"} for i in ids]})
        if self.path.rstrip("/") == "/spend":
            day, month = self.spend.totals()
            return self._send_json(200, {"today_usd": round(day, 4), "month_usd": round(month, 4),
                                         "limits": self.cfg["budget"], "status": self.spend.status()})
        self._send_json(404, {"error": {"message": "not found"}})

    def do_POST(self):
        if not self._authorized():
            return self._send_json(401, {"error": {"message": "bad router token"}})
        if self.path.rstrip("/") not in ("/v1/chat/completions", "/chat/completions"):
            return self._send_json(404, {"error": {"message": "not found"}})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        except ValueError:
            return self._send_json(400, {"error": {"message": "invalid JSON"}})

        self.info.refresh()
        try:
            upstream, d = decide(body, self.cfg, self.info, self.spend)
        except BudgetExceeded as e:
            day, month = e.args[0]
            return self._send_json(429, {"error": {"message": f"Router budget reached (today ${day:.2f}, month ${month:.2f}). "
                                                              "Raise limits in router/config.json or wait for the reset."}})
        meta = {"X-Router-Tier": d["tier"], "X-Router-Effort": str(d["effort"]), "X-Router-Reason": d["reason"][:120]}

        req = urllib.request.Request(OPENROUTER + "/chat/completions", data=json.dumps(upstream).encode(), method="POST",
                                     headers={"Authorization": "Bearer " + self.api_key, "Content-Type": "application/json",
                                              "X-Title": "balaji-router"})
        try:
            resp = urllib.request.urlopen(req, timeout=300)
        except urllib.error.HTTPError as e:
            return self._send_json(e.code, _safe_json(e.read()), meta)
        except Exception as e:
            return self._send_json(502, {"error": {"message": "upstream unreachable: %s" % e}}, meta)

        with resp:
            if upstream.get("stream"):
                self._stream(resp, meta, d)
            else:
                data = _safe_json(resp.read())
                usd = cost_of(data.get("usage"), data.get("model"), self.info)
                self.spend.add(usd)
                self._log(d, data.get("model"), usd)
                data["x_router"] = {k: d[k] for k in ("tier", "reason", "effort")}
                self._send_json(200, data, meta)

    def _stream(self, resp, meta, d):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self._cors()
        for k, v in meta.items():
            self.send_header(k, v)
        self.end_headers()
        usage, model = None, None
        for line in resp:
            self.wfile.write(line)
            self.wfile.flush()
            if line.startswith(b"data: {"):
                try:
                    chunk = json.loads(line[6:])
                except ValueError:
                    continue
                model = chunk.get("model") or model
                usage = chunk.get("usage") or usage
        usd = cost_of(usage, model, self.info)
        self.spend.add(usd)
        self._log(d, model, usd)

    def _log(self, d, model, usd):
        print(json.dumps({"t": time.strftime("%Y-%m-%d %H:%M:%S"), "tier": d["tier"], "reason": d["reason"],
                          "effort": d["effort"], "model": model, "usd": round(usd, 6)}), flush=True)


def _safe_json(raw):
    try:
        return json.loads(raw)
    except ValueError:
        return {"error": {"message": raw.decode("utf-8", "replace")[:500]}}


# --------------------------------------------------------------------------- CLI

def cmd_check(cfg, info):
    if not info.refresh(force=True):
        print("Could not reach OpenRouter; nothing verified.")
        return 1
    bad = 0
    for tier, t in cfg["tiers"].items():
        for i, slug in enumerate(t["models"]):
            m = info.live.get(slug)
            if not m:
                print(f"MISSING  {tier}: {slug} is not in OpenRouter's model list")
                bad += 1
                continue
            eff = info.efforts(slug)
            used = clamp_effort(t["effort"], eff) if i == 0 else t["effort"]
            note = "" if used == t["effort"] else f"  (asked {t['effort']}, will send {used})"
            print(f"ok       {tier}: {slug}  efforts={eff}{note}")
            snap = cfg["models"].get(slug, {}).get("efforts")
            if snap is not None and eff is not None and snap != eff:
                print(f"         config snapshot efforts {snap} differ from live {eff}; live wins at runtime")
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", metavar="PROMPT", help="show the routing decision for a prompt and exit")
    ap.add_argument("--model", default="router/auto", help="with --dry-run: requested model name")
    ap.add_argument("--live", action="store_true", help="with --dry-run: use live OpenRouter effort lists")
    ap.add_argument("--check", action="store_true", help="verify configured slugs and efforts against the live model list")
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--config")
    args = ap.parse_args()

    cfg = load_config(args.config)
    info = ModelInfo(cfg)

    if args.check:
        sys.exit(cmd_check(cfg, info))
    if args.dry_run is not None:
        if args.live:
            info.refresh(force=True)
        body = {"model": args.model, "messages": [{"role": "user", "content": args.dry_run}]}
        _, d = decide(body, cfg, info)
        print(json.dumps(d, indent=2))
        return
    if args.serve:
        key = os.environ.get("OPENROUTER_API_KEY", "")
        if not key:
            sys.exit("Set OPENROUTER_API_KEY first (never put the key in config.json).")
        Handler.cfg, Handler.info, Handler.api_key = cfg, info, key
        Handler.spend = Spend(cfg)
        Handler.token = os.environ.get("ROUTER_TOKEN", "")
        if args.host != "127.0.0.1" and not Handler.token:
            sys.exit("Refusing to listen on a public address without ROUTER_TOKEN set.")
        info.refresh(force=True)
        print(f"[router] listening on http://{args.host}:{args.port}/v1  (budget: {cfg['budget']})", flush=True)
        ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
        return
    ap.print_help()


if __name__ == "__main__":
    main()
