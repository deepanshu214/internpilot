# InternPilot: setup checklist (the parts only you can do)

Everything else is built and tested (45 tests). Work top to bottom; each step ends with a ✅ check.
Total: about 60–75 minutes. Steps 1–4 already give you a working system; 5–8 add the cloud dashboard and email.

> **Never get charged:** see the bottom of this file. Short version: never add a payment method anywhere.
>
> **Check your progress any time:** `.venv/bin/python scripts/doctor.py` shows ✅/❌ for every step, with the next action.
> It only makes free read-only calls, so it uses no AI quota and sends nothing.

All commands run from the project folder:
```bash
cd ~/Desktop/internpilot && cp -n .env.example .env
```

---

## 1. Review your profile (10 min). Do this first.
Everything is generated from `profile/profile.yaml`, and the resume tailor may never add anything that isn't in it.
- Add your **LinkedIn URL** under `links:`, plus the **GitHub URLs** of MoodSpace, Margdarshak and Secure IPC (`url:`).
- Check every bullet is true and phrased how you like it.
- Skim `profile/answers.yaml` (the form-filling answers bank).
- ✅ `.venv/bin/python -m pytest -q` still passes.

## 2. Telegram alerts + buttons (5 min)
1. In Telegram, message **@BotFather** → `/newbot` → copy the token into `.env` as `TELEGRAM_BOT_TOKEN=`.
2. Send any message to your new bot, then run `.venv/bin/python scripts/telegram_chat_id.py` → put the number in `TELEGRAM_CHAT_ID=`.
- ✅ `.venv/bin/python -m worker.scheduler --once` → alerts arrive with **✅ Shortlist & prepare / ⏭ Skip** buttons.

## 3. Free AI keys: Groq + Gemini (5 min, no card needed)
1. **Groq** → https://console.groq.com → sign in → **API Keys → Create** → `.env`: `GROQ_API_KEY=`
   - Stay on the **Free** plan. Never click *Upgrade* and never add a card.
2. **Gemini** → https://aistudio.google.com → **Get API key → Create API key** → `.env`: `GEMINI_API_KEY=`
   - Use a project with **no billing account**. Ignore any "set up billing" or "buy credits" prompts.
- ✅ The run log says `llm: groq_small`, and the dashboard → **Activity → AI usage & cost** shows calls and **Cost: $0.00**.
- How the bot stays free: Groq's small model scores jobs, Groq's 70B writes emails and resumes, and Gemini is the backup.
  Daily caps in `config/settings.yaml` sit below each free limit. When one is hit, the bot switches to the next free option,
  then to keyword scoring and templates. If Groq ever reports paid-plan limits, you get a Telegram warning.
- Ollama is optional now (skip it on your 8 GB Mac).

## 4. Start the always-on worker (2 min)
```bash
./scripts/install_launchd.sh
```
- ✅ `tail -f logs/worker.log` shows `worker started`, and the dashboard sidebar says **Worker online**.
- Local dashboard any time: `cd web && npm run dev` → http://localhost:3000

## 5. Gmail: reply tracking, job-alert emails, sending (15 min)
1. https://console.cloud.google.com → create a project "InternPilot".
2. **APIs & Services → Library → Gmail API → Enable**.
3. **OAuth consent screen**: External, app name InternPilot, your email. Under **Test users**, add `deepanshuagarwal10b@gmail.com`.
4. **Credentials → Create credentials → OAuth client ID → Desktop app**. Download the JSON and save it as
   `secrets/gmail_credentials.json`.
5. Run `.venv/bin/python scripts/gmail_auth.py` and approve in the browser (it only asks to *send* and *read*).
- ✅ It prints `Authorized as deepanshuagarwal10b@gmail.com`.
- Then on the OAuth consent screen click **Publish app → In production**. Ignore the "verification" notice: it's fine for
  personal use. In *Testing* mode, Google expires the login every 7 days.
- Outreach stays a **dry run** (emails are written to `outbox/*.eml`, nothing sent) until you set `DRY_RUN=0` in `.env`.
  Approve one email in the dashboard first, open the `.eml`, and only then switch it on.

## 6. Job alerts for platforms with no public feed (10 min)
Create job alerts, delivered to this Gmail, on: **LinkedIn** (Jobs → search "intern" + India → *Set alert*), **Wellfound**,
**Naukri**, **Instahyre**, **Cutshort**, **Internshala**. The worker parses those emails into your inbox automatically.

## 7. Supabase database (10 min). Needed for the dashboard on your phone.
1. https://supabase.com → New project "internpilot" (free tier, region **Mumbai**). Save the DB password.
2. **Project Settings → Database → Connection string**:
   - **Session pooler** URI (port 5432) → `.env` as `DATABASE_URL=` (used by the worker)
   - **Transaction pooler** URI (port 6543) → for Vercel (step 8)
3. Copy what you've collected so far: `.venv/bin/python scripts/copy_to_supabase.py`
4. Restart the worker: `./scripts/install_launchd.sh`
- ✅ The script prints row counts (about 500 jobs).

## 8. Deploy the dashboard to Vercel (10 min)
1. ~~Push to GitHub~~ Done: https://github.com/deepanshu214/internpilot (public; personal details such as your phone number live only in `.env`).
2. Vercel → Add New Project → import `deepanshu214/internpilot` → **Root Directory: `web`**.
3. Environment variables:
   - `DATABASE_URL` = the **Transaction pooler** URI from 7.2
   - `DASHBOARD_PASSWORD` = a strong password
   - `DASHBOARD_SECRET` = the output of `openssl rand -hex 32`
4. Deploy, then put the URL in `.env` as `DASHBOARD_URL=` (makes the Telegram "Dashboard" buttons work) and restart the worker.
- ✅ The deployed URL asks for your password, then shows your inbox.

## 9. Optional extras
- **Hunter.io** free key (25 lookups/month, finds real recruiter emails) → `HUNTER_API_KEY=`.
- First real autofill: in the dashboard open a Greenhouse or Lever job → **Open & autofill on Mac**. A browser opens,
  fills the form, outlines what needs you in orange, and outlines Submit in red. **You** check everything and submit.
- Tune `config/settings.yaml`: locations, search terms, `alert_threshold`, `daily_cap`. Use `mode: job` later for full-time roles.

---

## Never get charged: every service used, and how it stays $0
| Service | What it's for | Free as long as… | If you hit a limit |
|---|---|---|---|
| Groq | job scoring, emails, resume wording | you stay on the Free plan (no card) | 429 → bot uses Gemini / templates |
| Gemini | backup writer | the API key's project has **no billing account** | 429 → templates |
| Supabase | database | Free plan, no card (500 MB; we use a few MB a month) | it restricts the project; it doesn't bill |
| Vercel | dashboard hosting | Hobby plan, no card | it pauses; it doesn't bill |
| GitHub | public repo | free plan | n/a |
| Telegram, Gmail API | alerts, email | always free | n/a |
| Hunter.io (optional) | recruiter emails | Free plan (25 searches/month), no card | searches stop until next month |
| Job sources | discovery | public pages/APIs, no accounts | a source is skipped that run |

The bot also guards the AI side itself:
- daily caps below every free limit (`config/settings.yaml → llm`);
- a Telegram note at 80% of a cap;
- a warning if Groq reports paid-plan limits;
- a live **AI usage & cost** card on the dashboard's Activity page.
