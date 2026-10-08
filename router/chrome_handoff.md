# Handoff notes for Claude in Chrome (paste one note per session)

Run Note A first, then the router step, then Note B.

---

## Note A: OpenRouter

```
You are helping the owner of three small businesses in Vadodara set up OpenRouter (openrouter.ai) in their own Chrome. First call tabs_context_mcp and look for tabs already open on openrouter.ai; reuse those. If none exist, open a new tab.

GOAL: a safe, capped OpenRouter setup that a local routing script will use.

DO, in this order:
1. Open https://openrouter.ai/settings/keys. Report whether the owner is signed in. If not, stop and ask them to sign in; never enter passwords.
2. Report the current credit balance and whether any key already exists (names only).
3. Create ONE new API key named "balaji-router" with a credit limit of $10 (monthly reset if offered, otherwise total). When the key value is displayed, STOP and tell the owner to copy it themselves into their computer's OPENROUTER_API_KEY variable. Do not read it out, type it anywhere, or repeat it in chat.
4. Open https://openrouter.ai/settings/routing (Auto Router section). Report what is currently saved. Do not change it: the owner's script handles routing.
5. Open the Guardrails section (Settings > Privacy > Guardrails). Report whether a spending cap exists. Propose, but do not create without approval: daily cap $1, monthly cap $10, apply to the key "balaji-router".
6. Report back: signed in yes/no, credits, key created yes/no, limits set, guardrail status, anything unexpected.

DO NOT without asking the owner first and getting a clear yes in this chat:
- add credits, enter payment details, or start any subscription or purchase
- delete or edit existing keys
- change privacy, data-collection, or account settings
- enable BYOK or connect other provider keys

STOP and ask if: a page will not load after 2 attempts, a dialog or CAPTCHA appears, the layout differs from what is described, or any step needs payment. Describe what you see and what you tried. Do not guess at buttons.
Keep your reports short: bullets, no more than 10 lines.
```

---

## Router step (owner, on their own computer, in a terminal)

```
git pull origin claude/funny-gauss-yk826r
cd router
python3 -m unittest test_router
python3 router.py --check
export OPENROUTER_API_KEY=<paste your key here, in the terminal only>
python3 router.py --serve
```
Leave the terminal open. The router listens at http://127.0.0.1:8787/v1 and spend is at http://127.0.0.1:8787/spend.

---

## Note B: TypingMind

```
You are helping the owner of three small businesses in Vadodara set up TypingMind (typingmind.com) in their own Chrome. First call tabs_context_mcp and look for tabs already open on typingmind.com; reuse those. If none exist, open a new tab.

GOAL: TypingMind uses a local routing script as a custom model endpoint, with three folders, one per business.

BEFORE STARTING, check: the owner's local router is running at http://127.0.0.1:8787. Open http://127.0.0.1:8787/v1/models in a new tab. It should list router/auto, router/simple, router/standard, router/hard, router/sensitive. If it does not, stop and tell the owner to start the router.

DO, in this order:
1. Report whether TypingMind is open, signed in or licensed, and the plan shown. If a license is missing, STOP; do not buy anything.
2. Go to Manage Models, then Add Custom Model. Add these models, one each, with endpoint http://127.0.0.1:8787/v1/chat/completions and the model ID exactly as listed:
   router/auto, router/hard, router/simple, router/standard
   Use the display names "Router Auto", "Router Hard (WVS)", "Router Simple", "Router Standard". Where an API key field is required, leave it blank or ask the owner; a router token exists only if they set ROUTER_TOKEN, so ask.
   Field labels may differ from this note. Describe what you see before filling anything unfamiliar.
3. Send one test message to Router Auto: "Write 3 hooks for a Reel about home loan documents". Report the answer length and, if visible, which tier/model answered (the router adds an x_router field and X-Router-Tier header).
4. Create three folders: "WVS", "CSC Balaji", "UCF". For each, set the default model (WVS: Router Hard; CSC Balaji: Router Auto; UCF: Router Auto).
5. For each folder, paste the custom instructions the OWNER provides from router/typingmind_folder_prompts.md. If they have not pasted them in this chat, stop and ask. Never invent, shorten or "improve" the prompts. The CSC Balaji and UCF prompts contain [BRACKETS] the owner must fill first.
6. Report back: models added, test result, folders created, anything unexpected.

DO NOT without a clear yes from the owner in this chat:
- purchase or renew a license, enter payment details
- paste or type any API key (the owner does this)
- delete chats, folders or existing models
- connect MCP connectors or third-party accounts (a later, separate step)

STOP and ask if: the browser blocks calls to 127.0.0.1 (report the exact error), a page will not load after 2 attempts, a dialog or CAPTCHA appears, or the screen differs from this note. Do not guess.
Keep your reports short: bullets, no more than 10 lines.
```

---

Checks the owner should do after both notes finish
- Open http://127.0.0.1:8787/spend: today's and this month's spend should be near $0 after the test message.
- Send one SIP caption in the WVS folder and confirm the answer carries the ARN line and the market risk disclaimer.
- Send one fake chat containing a made-up PAN (for example ABCDE1234F) and confirm the router log shows tier "sensitive".
