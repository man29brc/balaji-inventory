# Query router for OpenRouter

Picks the model **and** reasoning effort for each chat message, enforces a daily/monthly USD budget, and keeps customer data off cheap models. OpenAI-compatible, standard library only (Python 3.9+).

| Tier | Triggers | Models (primary → fallback) | Effort |
|---|---|---|---|
| `simple` | caption, hook, hashtag, translate, rewrite… | `z-ai/glm-5.3-flash` → `google/gemini-3.1-flash-lite` | low |
| `standard` | plan, analyse, strategy, anything unclear | `deepseek/deepseek-v4.1-flash` → `google/gemini-3.7-flash` | high |
| `hard` | mutual fund / SIP / insurance / SEBI / IRDAI words | `anthropic/claude-sonnet-5.5` → `google/gemini-3.1-pro-preview` | high |
| `sensitive` | PAN, Aadhaar, phone, email found in the chat | same as `hard`, zero-data-retention only | medium |

Rules that are always on:
- Sensitive data beats everything, even a forced tier.
- `hard` is never downgraded for budget. `standard` drops to `simple` once 80% of a daily or monthly limit is used. At 100% every request gets a 429.
- The tier's privacy settings override whatever the chat app sends.
- Effort is clamped to what the primary model accepts (live list from OpenRouter, config snapshot if offline).

## Use it

```bash
cd router
python3 -m unittest test_router          # offline tests
python3 router.py --check                # verify slugs/efforts against OpenRouter (no key needed)
python3 router.py --dry-run "write a caption" --live
export OPENROUTER_API_KEY=sk-or-...      # use a key with a credit limit set in OpenRouter
python3 router.py --serve                # http://127.0.0.1:8787/v1
```

In TypingMind add a custom model with endpoint `http://127.0.0.1:8787/v1/chat/completions` and model IDs `router/auto`, `router/simple`, `router/standard`, `router/hard`. Pin `router/hard` in the WVS folder. Check spend at `http://127.0.0.1:8787/spend`.

To use it from the TypingMind web app on a phone, the router must be reachable over HTTPS from the internet. Then set `ROUTER_TOKEN` (the server refuses a public address without it) and put the same token in TypingMind as the API key.

## Not verified yet
- Live calls to OpenRouter (no key was available when this was built). Streaming and cost tracking are tested against a fake upstream only.
- Whether OpenRouter applies the primary model's `reasoning.effort` correctly when it falls back to Gemini. The first fallback you trigger will show in the log line.
- Gujarati/Hindi quality of the cheap models. Run 5 real prompts through `router/simple` before trusting it.
- Keyword rules are simple on purpose. Words like `returns`, `premium` and `nav` send ordinary prompts to `hard`, which costs more but errs on the safe side. Edit `config.json` `rules` to tune.

The router is a helper, not a compliance check: anything for WVS still goes through your compliance review before you approve it.
