import base64

import pytest

from worker import llm
from worker.config import PROFILE
from worker.db import DB
from worker.match.skills import profile_skills
from worker.models import Job
from worker.tailor import select as select_mod
from worker.tailor.render import page_count
from worker.tailor.service import tailor
from worker.tailor.validate import check_bullet, validate_selection

NETGUARD = next(p for p in PROFILE["projects"] if p["name"].startswith("NetGuard"))
K8S_JD = ("Security Engineering Intern. Requirements: Kubernetes, Terraform, Go, network security, intrusion detection, "
          "Python. You will harden our Kubernetes clusters.")


@pytest.fixture
def db(tmp_path):
    d = DB(url="", sqlite_path=str(tmp_path / "t.db"))
    job = Job(source="test", company="Acme", title="Security Engineering Intern", location="Remote", url="https://x",
              jd_text=K8S_JD)
    d.insert_job(job, None)
    d.upsert_match(job.id, 80, [], [], "heuristic")
    d.job_id = job.id
    return d


def test_validator_rejects_invented_skills_and_numbers():
    original = NETGUARD["bullets"][0]
    assert check_bullet(original, original, NETGUARD) is None
    assert "Kubernetes" in check_bullet(original + " Deployed on Kubernetes.", original, NETGUARD)
    assert "numbers" in check_bullet(original.replace("6 stateful", "12 stateful"), original, NETGUARD)
    assert "numbers" in check_bullet(original + " Cut false positives by 40%.", original, NETGUARD)
    assert check_bullet("I built a NIDS.", original, NETGUARD) == "first person"


def test_validator_allows_skills_from_same_item():
    original = NETGUARD["bullets"][1]
    reworded = "Streamed real-time alerts over WebSockets with a μ + 2σ statistical baseline separating benign bursts from volumetric attacks."
    assert check_bullet(reworded, original, NETGUARD) is None


def test_heuristic_selection_never_adds_missing_skills():
    sel = select_mod.heuristic_selection(K8S_JD, title="Security Engineering Intern")
    assert validate_selection(sel) == []
    every_skill = {s for group in sel["skills"].values() for s in group}
    assert every_skill <= set(profile_skills())
    assert "Kubernetes" not in every_skill and "Terraform" not in every_skill
    assert sel["projects"][0]["name"].startswith("NetGuard")  # domain-relevant project first


def test_llm_rewrites_are_filtered(monkeypatch):
    b0, b1 = NETGUARD["bullets"][0], NETGUARD["bullets"][1]
    fake = {
        "projects": [NETGUARD["name"], "Made Up Project"],
        "summary": "Security-focused CS student who has run Kubernetes in production.",
        "bullets": {b0: b0 + " Deployed on Kubernetes.",  # invented skill → rejected
                    b1: "Streamed live telemetry and alerts over WebSockets using a statistical baseline (μ + 2σ) to tell "
                        "benign bursts from volumetric attacks."},  # faithful → accepted
    }
    monkeypatch.setattr(llm, "available", lambda: "ollama")
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: fake)
    sel = select_mod.select(K8S_JD, title="Security Engineering Intern")
    assert [p["name"] for p in sel["projects"]] == [NETGUARD["name"]]  # unknown project ignored
    bullets = sel["projects"][0]["bullets"]
    assert b0 in bullets and not any("Kubernetes" in b for b in bullets)
    assert any(r["original"] == b0 for r in sel["rejected"])
    assert len(sel["rephrased"]) == 1
    assert sel["summary"] == PROFILE["summary"]  # fabricated summary rejected
    assert validate_selection(sel) == []


def test_tailor_end_to_end_one_page(db, monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "available", lambda: None)
    monkeypatch.setattr("worker.tailor.service.OUTPUT_DIR", tmp_path)
    out = tailor(db, db.job_id)
    row = db.one("select * from resumes where id = ?", (out["resume_id"],))
    pdf = base64.b64decode(row["pdf_b64"])
    assert pdf.startswith(b"%PDF") and page_count(pdf) == 1
    assert db.get("matches", db.job_id, key="job_id")["status"] == "tailored"
    assert tailor(db, db.job_id)["version"] == 2


def test_trimming_keeps_one_page(monkeypatch, tmp_path):
    from worker.tailor.render import render_one_page
    sel = select_mod.heuristic_selection(K8S_JD, max_projects=6)
    for p in sel["projects"]:  # pad every project to overflow the page
        p["bullets"] = p["bullets"] * 3
        p["drop_order"] = list(range(len(p["bullets"])))
    pdf, final = render_one_page(sel)
    assert page_count(pdf) == 1
    assert sum(len([b for b in p["bullets"] if b]) for p in final["projects"]) < sum(
        len(p["bullets"]) for p in sel["projects"])
