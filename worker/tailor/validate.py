"""Anti-fabrication checks. A tailored resume may only select, reorder and rephrase what's in profile.yaml.
Anything that introduces a skill, tool or number not present in the source item is rejected."""
import re

from ..config import PROFILE
from ..match.skills import MARKET_SKILLS, find_skills, profile_skills

ALL_SKILLS = sorted(set(profile_skills()) | set(MARKET_SKILLS))
_NUM = re.compile(r"\d+(?:[.,]\d+)?")
_FIRST_PERSON = re.compile(r"\b(I|me|my|mine)\b")


def item_text(item: dict) -> str:
    parts = [item.get("name", ""), item.get("org", ""), item.get("role", ""), item.get("pitch", ""),
             " ".join(item.get("stack", [])), " ".join(item.get("tags", [])), " ".join(item.get("bullets", []))]
    return " ".join(parts)


def check_text(new: str, source: str, max_len: int | None = None) -> str | None:
    """Return a reason string if `new` isn't a faithful rephrase of `source`, else None."""
    if not new or not new.strip():
        return "empty"
    added = find_skills(new, ALL_SKILLS) - find_skills(source, ALL_SKILLS)
    if added:
        return f"introduces skills not in the source: {', '.join(sorted(added))}"
    new_nums = set(_NUM.findall(new)) - set(_NUM.findall(source))
    if new_nums:
        return f"introduces numbers not in the source: {', '.join(sorted(new_nums))}"
    if _FIRST_PERSON.search(new):
        return "first person"
    if max_len and len(new) > max_len:
        return f"too long ({len(new)} > {max_len})"
    return None


def check_bullet(new: str, original: str, item: dict) -> str | None:
    return check_text(new, item_text(item), max_len=int(len(original) * 1.35) + 30)


def find_item(name: str, kind: str) -> dict | None:
    key = "name" if kind == "projects" else "org"
    return next((x for x in PROFILE[kind] if x[key] == name), None)


def validate_selection(sel: dict) -> list[str]:
    """All problems in a selection (empty list = safe to render)."""
    problems = []
    mine = set(profile_skills())
    for group, skills in sel.get("skills", {}).items():
        extra = set(skills) - mine
        if extra:
            problems.append(f"skills group {group}: not in profile: {', '.join(sorted(extra))}")
    for kind in ("projects", "experience"):
        for entry in sel.get(kind, []):
            item = find_item(entry["name"], kind)
            if not item:
                problems.append(f"{kind}: unknown item {entry['name']!r}")
                continue
            for b in entry["bullets"]:
                if b is None or b in item["bullets"]:
                    continue
                if (reason := check_text(b, item_text(item))) is not None:
                    problems.append(f"{entry['name']}: bullet {b[:50]!r}: {reason}")
    if (reason := check_text(sel.get("summary", ""), PROFILE["summary"] + " " + " ".join(mine))) is not None:
        problems.append(f"summary: {reason}")
    return problems
