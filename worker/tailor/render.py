import copy
import io
import json
from pathlib import Path

import typst
from pypdf import PdfReader

from ..config import PROFILE

TEMPLATE = Path(__file__).with_name("resume.typ")
GROUP_NAMES = {"core_cs": "Core CS", "languages": "Languages", "web": "Frameworks / Web", "databases": "Databases",
               "ml": "Machine Learning", "security": "Security", "tools": "Developer Tools"}


def _display_name(name: str, stack: list[str]) -> str:
    """'NetGuard SOC — Real-Time ...' → 'NetGuard SOC' when name + stack wouldn't fit on one line."""
    return name.split(" — ")[0] if len(name) + len(", ".join(stack)) > 95 else name


def template_data(sel: dict) -> dict:
    p = PROFILE
    links = p.get("links", {})
    contacts = [{"label": p["phone"], "url": ""}, {"label": p["email"], "url": f"mailto:{p['email']}"}]
    contacts += [{"label": k.title() if k != "github" else "GitHub", "url": v} for k, v in links.items() if v]
    exp = {e["org"]: e for e in p["experience"]}
    proj = {x["name"]: x for x in p["projects"]}
    return {
        "name": p["name"],
        "contacts": contacts,
        "summary": sel["summary"],
        "education": p["education"],
        "experience": [{"name": e["name"], "role": exp[e["name"]]["role"], "dates": exp[e["name"]]["dates"],
                        "bullets": [b for b in e["bullets"] if b]} for e in sel["experience"]],
        "projects": [{"name": _display_name(x["name"], proj[x["name"]]["stack"]), "stack": proj[x["name"]]["stack"],
                      "url": proj[x["name"]].get("url") or "",
                      "bullets": [b for b in x["bullets"] if b]} for x in sel["projects"]],
        "skills": {GROUP_NAMES.get(g, g.replace("_", " ").title()): items for g, items in sel["skills"].items() if items},
        "certifications": sel.get("certifications", p.get("certifications", [])),
        "achievements": sel.get("achievements", p.get("achievements", [])),
    }


def compile_pdf(sel: dict) -> bytes:
    return typst.compile(str(TEMPLATE), sys_inputs={"data": json.dumps(template_data(sel))})


def page_count(pdf: bytes) -> int:
    return len(PdfReader(io.BytesIO(pdf)).pages)


def _trim_steps(sel: dict):
    """Progressively shorter versions of the selection, least valuable content first."""
    s = copy.deepcopy(sel)
    s.setdefault("achievements", list(PROFILE.get("achievements", [])))
    while len(s["achievements"]) > 1:
        s["achievements"].pop()
        yield copy.deepcopy(s)
    for kind in ("projects", "experience"):
        for entry in reversed(s[kind]):  # least relevant entry loses its least relevant bullets first
            order = list(entry.get("drop_order") or range(len(entry["bullets"]) - 1, -1, -1))
            while sum(b is not None for b in entry["bullets"]) > 2 and order:
                entry["bullets"][order.pop(0)] = None
                yield copy.deepcopy(s)
    while len(s["projects"]) > 2:
        s.setdefault("dropped_projects", []).append(s["projects"].pop()["name"])
        yield copy.deepcopy(s)
    s["achievements"] = []
    yield copy.deepcopy(s)


def render_one_page(sel: dict) -> tuple[bytes, dict]:
    """Compile; if it spills onto page 2, trim until it fits. Returns (pdf, final selection)."""
    pdf = compile_pdf(sel)
    if page_count(pdf) == 1:
        return pdf, sel
    for trimmed in _trim_steps(sel):
        pdf = compile_pdf(trimmed)
        if page_count(pdf) == 1:
            return pdf, trimmed
    raise ValueError("resume does not fit on one page even after trimming")
