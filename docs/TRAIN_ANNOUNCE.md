# Git train announce (paste to Slack / email)

**Oatmeal AI promotion train is live (14 Sep 2026).**

```text
feature/*  →  PR  →  GCP/*-staging  →  PR  →  GCP/*-testing  →  PR  →  main
                   staging Cloud Run         testing Cloud Run          production
```

**Rules**
1. Cut work from **current staging**, not from `main`.
2. Feature / fix / chore PRs go **only into staging**.
3. Promote with staging → testing, then testing → `main` (never skip testing).
4. Do **not** dump staging into `main`.
5. Production deploys use GitHub Environment `production` — requires reviewer approval (`@dbanoth` or `@OatmealAIJohn`).

**Repos:** OFN (`oatmealfarmnetwork`), LOA (`livestock-of-america`), Oatsense (`Oatsense-america-frontend`), backend (`oatmealfarmnetworkbackend`).

**Docs:** each repo `docs/BRANCHING.md` · Desktop `Oatmeal-AI-Branching-Strategy.md`.
