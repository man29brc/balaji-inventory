# Handoff notes for Claude in Chrome: run in parallel in tabs already open

Open two Claude sessions side by side. Paste Note A into one and Note B into the other. They run at the same time and do not depend on each other until the final step.

How the two connect:
- Note A makes the OpenRouter key. Only the owner copies it, into a terminal on their own computer.
- The owner then starts the router (commands below). Note B's test step waits for the owner's "router is running".
- Everything else in Note B (models, folders, prompts) needs no router and no key, so it can start immediately.

Before pasting: fill the [BRACKETS] in the CSC Balaji and UCF prompts in `typingmind_folder_prompts.md`. Paste the three finished prompts into the Note B session when asked.

---

## Note A: OpenRouter (use the tab already open on openrouter.ai)

```
You are helping the owner of three small businesses in Vadodara set up OpenRouter in their own Chrome.

TABS: Call tabs_context_mcp first. The owner already has a tab open on openrouter.ai. Use ONLY that tab (and tabs you open on openrouter.ai from it). Never touch, read, or navigate any other tab. Another Claude session is working in the owner's TypingMind tab at the same time, so leave it alone. If you cannot find an openrouter.ai tab, stop and ask.

GOAL: a safe, capped OpenRouter setup for a local routing script.

DO, in this order:
1. In the open tab, go to https://openrouter.ai/settings/keys. Report whether the owner is signed in. If not, stop and ask them to sign in; never enter passwords.
2. Report the credit balance and whether any key already exists (names only).
3. Create ONE new API key named "balaji-router" with a credit limit of $10 (monthly reset if offered, otherwise total). When the key value is shown, STOP and tell the owner to copy it themselves into their computer's terminal variable OPENROUTER_API_KEY. Do not read it out, type it anywhere, or repeat it in chat.
4. Open https://openrouter.ai/settings/routing and report what is saved in the Auto Router section. Do not change it.
5. Open the Guardrails section (Settings > Privacy > Guardrails) and report whether a spending cap exists. Propose, but do NOT create without the owner's yes: daily cap $1, monthly cap $10, applied to the key "balaji-router".
6. Report back in 10 lines or fewer: signed in yes/no, credits, key created yes/no, limits set, guardrail status, anything unexpected. End with: "Key created. Owner: copy it and start the router."

DO NOT without a clear yes from the owner in this chat:
- add credits, enter payment details, or start any purchase or subscription
- delete or edit existing keys
- change privacy, data-collection, or account settings
- enable BYOK or connect other provider keys

STOP and ask if: a page fails to load after 2 attempts, a dialog or CAPTCHA appears, the screen differs from this note, or any step needs payment. Describe what you see and what you tried. Do not guess at buttons.
```

---

## Router step (owner, on their own computer, in a terminal; after Note A says the key is created)

```
git pull origin claude/funny-gauss-yk826r
cd router
python3 -m unittest test_router
python3 router.py --check
export OPENROUTER_API_KEY=<paste your key here, in the terminal only>
python3 router.py --serve
```
Leave the terminal open. The router listens at http://127.0.0.1:8787/v1. Then tell the Note B session: "router is running".

---

## Note B: TypingMind (use the tab already open on typingmind.com)

```
You are helping the owner of three small businesses in Vadodara set up TypingMind in their own Chrome.

TABS: Call tabs_context_mcp first. The owner already has a tab open on typingmind.com. Use ONLY that tab for TypingMind work. Never touch, read, or navigate any other tab; another Claude session is working in the owner's OpenRouter tab at the same time. The one exception is PART 2, step 1, where you may open a NEW tab for the local check and close it afterwards. If you cannot find a typingmind.com tab, stop and ask.

PART 1: start now, no router needed.
1. Report whether TypingMind is signed in or licensed, and the plan shown. If a license is missing, STOP. Do not buy anything.
2. Go to Manage Models, then Add Custom Model. Add these four models, one each, endpoint http://127.0.0.1:8787/v1/chat/completions, model ID exactly as listed:
   router/auto  (display name "Router Auto")
   router/hard  ("Router Hard (WVS)")
   router/simple  ("Router Simple")
   router/standard  ("Router Standard")
   If an API key field is required, ask the owner what to enter; do not invent a value. Field labels may differ from this note: describe anything unfamiliar before filling it.
3. Create three folders: "WVS", "CSC Balaji", "UCF". Set default models: WVS = Router Hard (WVS); CSC Balaji = Router Auto; UCF = Router Auto.
4. For each folder, paste the custom instructions the OWNER gives you in this chat, exactly as given. If they have not pasted them, ask for them. Never invent, shorten, or "improve" a prompt. If a prompt still contains [BRACKETS], stop and tell the owner which ones.
5. Report in 10 lines or fewer: models added, folders created, prompts pasted, anything unexpected. End with: "Part 1 done. Waiting for 'router is running'."

PART 2: only after the owner says "router is running".
1. Open a NEW tab at http://127.0.0.1:8787/v1/models. It should list router/auto, router/simple, router/standard, router/hard, router/sensitive. Close that tab. If it fails or lists something else, STOP and report the exact error.
2. In the TypingMind tab, open a new chat with Router Auto and send: "Write 3 hooks for a Reel about home loan documents". Report whether an answer came back, how long it is, and whether any error appeared.
3. If the browser blocks the call to 127.0.0.1, STOP and report the exact error text.

DO NOT without a clear yes from the owner in this chat:
- purchase or renew a license, or enter payment details
- paste or type any API key (the owner does this)
- delete chats, folders, or existing models
- connect MCP connectors or third-party accounts (a separate later step)

STOP and ask if: a page fails to load after 2 attempts, a dialog or CAPTCHA appears, or the screen differs from this note. Do not guess.
```

---

Checks for the owner after both notes finish
- http://127.0.0.1:8787/spend should show about $0 after the test message.
- In the WVS folder, ask for one SIP caption. It must carry the ARN line and the market-risk disclaimer.
- Send a chat with a made-up PAN (for example ABCDE1234F) and confirm the router log shows tier "sensitive".
