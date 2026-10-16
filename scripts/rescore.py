"""Re-score your best keyword-scored matches with the free AI scorer (paced, within free caps).
Usage: .venv/bin/python scripts/rescore.py [how_many=30]"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from worker import llm  # noqa: E402
from worker.db import DB  # noqa: E402
from worker.match.score import llm_score  # noqa: E402
from worker.match.skills import skill_gap  # noqa: E402
from worker.models import Job  # noqa: E402

if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    db = DB()
    llm.use_db(db)
    rows = db.query("select j.*, m.score from jobs j join matches m on m.job_id = j.id where m.status = 'new'"
                    " and m.method = 'heuristic' order by m.score desc, length(j.jd_text) desc limit ?", (n,))
    done = 0
    for r in rows:
        if not llm.available("score"):
            print("free AI cap reached for today, stopping (keyword scores kept)")
            break
        job = Job(r["source"], r["company"], r["title"], r["location"] or "", r["url"], r["jd_text"] or "")
        out = llm_score(job, skill_gap(job.jd_text)[1])
        if not out:
            continue
        reasons = out.get("reasons") or []
        if out.get("eligibility_issue"):
            reasons = [f"⚠️ {out['eligibility_issue']}", *reasons]
        if out.get("best_project"):
            reasons.append(f"Pitch: {out['best_project']}")
        db.upsert_match(r["id"], out["score"], reasons, out.get("missing_skills") or [], llm.last_provider or "llm")
        done += 1
        print(f"{r['score']:>3} → {out['score']:>3}  {r['title'][:60]} @ {r['company'][:30]}")
    print(f"re-scored {done} matches")
