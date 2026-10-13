# InternPilot

Personal internship radar: pulls postings from every platform with a public feed, scores them against
`profile/profile.yaml`, and alerts you on Telegram. Later phases add resume tailoring, recruiter outreach and a dashboard.

## Sources
| Platform | How | Login? |
|---|---|---|
| LinkedIn, Indeed, Naukri, Glassdoor, Google Jobs | `python-jobspy` (public search) | No |
| Internshala | public listing pages | No |
| Unstop | public search API | No |
| Greenhouse / Lever / Ashby companies | official job-board APIs (`config/watchlist.yaml`) | No |
| NVIDIA, Adobe, Intel, Salesforce, Cisco, … | Workday public JSON (`watchlist.yaml → workday`) | No |
| Amazon | amazon.jobs search JSON | No |
| SimplifyJobs Summer 2027 list | GitHub JSON | No |
| Remotive, RemoteOK, HN "Who is hiring?" | public APIs | No |
| Wellfound, Instahyre, Cutshort, LinkedIn alerts | via Gmail job-alert emails (Phase 6) | read-only Gmail |

## Run
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env            # fill in Telegram (+ optional Groq / Supabase)
.venv/bin/python -m worker.scheduler --once    # one run
./scripts/install_launchd.sh                   # every 3 h in the background
.venv/bin/python -m pytest -q
```
Without Ollama/Groq, scoring falls back to keyword + similarity heuristics (capped below "apply today").
With 8 GB RAM use `ollama pull qwen2.5:7b && ollama pull nomic-embed-text`.

Tune everything in `config/settings.yaml` (locations, title filters, thresholds, `mode: job` for full-time).
