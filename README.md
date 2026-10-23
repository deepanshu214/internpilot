# InternPilot

![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12-blue.svg)
![Next.js](https://img.shields.io/badge/Next.js-14-black.svg)
![Tests](https://img.shields.io/badge/tests-72%20passed-brightgreen.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Architecture](https://img.shields.io/badge/architecture-Microservice%20Worker-orange.svg)

Personal internship copilot. It finds internships on every platform with a public feed, scores them against your
profile, tailors a one-page resume per job, finds people to email and drafts the email, pre-fills applications, and
tracks replies. **Nothing is ever submitted or sent without your click.**

Setup steps that need your accounts: **[SETUP_TONIGHT.md](SETUP_TONIGHT.md)**.

Personal contact details and every key live in `.env` (git-ignored); `profile/profile.yaml` holds only resume content.

## How it fits together
```
 Mac worker (launchd, python -m worker.agent)                 Cloud
 ├─ discovery every 3 h ── 15+ sources ──┐                    ┌──────────────────────────┐
 ├─ matching (Groq / Gemini / heuristic)  ├──► Postgres ◄──────┤ Next.js dashboard (Vercel)│
 ├─ task queue: tailor · contacts · drafts│   (Supabase)       │ inbox · pipeline · job    │
 │   send · autofill · prep · cover letter│   or local SQLite  │ page · outreach · insights│
 ├─ Gmail: replies, OA/interview/rejection┘                    └──────────────────────────┘
 └─ Telegram: alerts with Shortlist/Skip buttons, daily digest, weekly review
```

## Sources
| Platform | How | Login? |
|---|---|---|
| LinkedIn, Indeed, Naukri, Glassdoor, Google Jobs | `python-jobspy` (public search) | No |
| Internshala · Unstop | public listing pages / search API | No |
| Greenhouse / Lever / Ashby companies | official job-board APIs (`config/watchlist.yaml`) | No |
| NVIDIA, Adobe, Intel, Salesforce, Cisco, Mastercard, PayPal | Workday public JSON | No |
| Amazon · SimplifyJobs list · Remotive · RemoteOK · HN "Who is hiring?" | public JSON | No |
| LinkedIn alerts, Wellfound, Instahyre, Cutshort, Naukri alerts… | your job-alert emails (read-only Gmail) | Gmail |

## Safety rails
- **$0 to run**: AI uses free tiers only (Groq small model for scoring, Groq 70B for writing, Gemini as backup), with
  daily caps below the free limits, automatic fallback, paid-plan detection, and a usage & cost card in the dashboard.
- **Resume tailor** only selects, reorders and rephrases `profile/profile.yaml`. A validator rejects any rewrite that adds a
  skill or number not in the source item (`worker/tailor/validate.py`), and the result is forced onto one page.
- **Emails**: drafts only; sending requires *Approve* on that draft; daily cap (15); `DRY_RUN=1` by default writes
  `outbox/*.eml`; one follow-up draft per thread, also needing approval. Draft text is checked for invented skills or numbers.
- **Autofill** fills and highlights fields, never clicks submit (tested against forms whose submit button says "Apply"),
  and never answers EEO, sponsorship or salary questions.
- **No logged-in LinkedIn automation.**
- **Dashboard**: password + signed cookie; the deployed app refuses to run without `DASHBOARD_PASSWORD`;
  Supabase tables have RLS on.

## Commands
```bash
.venv/bin/python -m worker.scheduler --once     # one discovery run
.venv/bin/python -m worker.agent                # the always-on worker (what launchd runs)
./scripts/install_launchd.sh                    # install/restart the worker in the background
cd web && npm run dev                           # dashboard on http://localhost:3000
.venv/bin/python scripts/doctor.py              # setup checker: ✅/❌ per step, free read-only calls
.venv/bin/python -m pytest -q                   # 72 tests (TEST_DATABASE_URL=<local postgres> runs them on Postgres)
```

## Layout
`worker/sources` discovery · `worker/match` scoring · `worker/tailor` resume (Typst) · `worker/outreach` domain/brief,
contacts, drafts, send, follow-ups · `worker/apply` Playwright autofill · `worker/tracking` inbox status ·
`worker/notify` Telegram, digest · `worker/docs.py` prep pack, cover letter · `worker/tasks.py` queue ·
`web/` dashboard · `supabase/migrations` schema (shared by SQLite and Postgres).
