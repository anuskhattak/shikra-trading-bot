---
id: PHR-0001
title: Project Structure and Config Review Agent Setup
stage: general
date: 2026-05-11
surface: agent
model: claude-sonnet-4-6
feature: none
branch: master
user: anaskhattak
command: /sp.phr
labels: [project-structure, config, review-agent, slash-command, setup]
links:
  spec: null
  ticket: null
  adr: null
  pr: null
files:
  - src/__init__.py
  - src/engine/__init__.py
  - src/risk/__init__.py
  - src/broker/__init__.py
  - src/filters/__init__.py
  - tests/__init__.py
  - tests/unit/__init__.py
  - tests/integration/__init__.py
  - tests/backtest/__init__.py
  - logs/trades.json
  - logs/false_signals.json
  - requirements.txt
  - .env.example
  - config.yaml
  - .gitignore
  - .claude/commands/review-config.md
tests:
  - none
---

## Prompt

User ne project structure banana shuru karne ka kaha. Is session mein:
1. constitution.md vs CLAUDE.md overlap discuss hua — constitution.md delete kiya
2. CLAUDE.md ko professional constitution pattern ke against evaluate kiya
3. Project folder structure create kiya (src/, tests/, backtest/, specs/, history/, logs/)
4. Config files banaye: requirements.txt, .env.example, config.yaml, .gitignore
5. config.yaml mein timeframe ghalat tha (M15/M1) — user ne D1/H4/H1 correct kiya
6. /review-config slash command banaya jo config.yaml ko CLAUDE.md requirements ke against validate karta hai

## Response snapshot

Pura project skeleton create kiya gaya — CLAUDE.md mein defined saari directories aur files ban gayi. config.yaml mein timeframes user input se correct kiye gaye (D1 HTF, H4 MTF, H1 LTF). Ek reusable `/review-config` slash command banaya gaya jo kabhi bhi config.yaml ko Shikra requirements ke against validate kar sakta hai.

## Outcome

- ✅ Impact: Shikra trading bot ka pura project skeleton ready hai — folders, Python packages, config files, aur review tooling sab set ho gaya
- 🧪 Tests: none — setup phase, koi code nahi likha
- 📁 Files: 16 files created/modified (structure + config + slash command)
- 🔁 Next prompts: MT5 Broker Connection feature specify karo — `/sp.specify MT5 broker connection feature`
- 🧠 Reflection: constitution.md aur CLAUDE.md ka overlap user ne khud pakda — single source of truth rakhna zyada clean approach hai

## Evaluation notes (flywheel)

- Failure modes observed: config.yaml mein timeframes guess se set kiye gaye the (M15/M1) — user ne correct kiya. Jab domain-specific values (timeframes, risk params) set karni hon to pehle user se confirm karna chahiye tha.
- Graders run and results (PASS/FAIL): none
- Prompt variant (if applicable): none
- Next experiment (smallest change to try): Config values set karne se pehle user se confirm karo — especially trading-specific parameters jo project se project alag hote hain
