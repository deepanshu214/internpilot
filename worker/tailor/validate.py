"""Anti-fabrication checks. A tailored resume may only select, reorder and rephrase what's in profile.yaml.
Anything that introduces a skill, tool or number not present in the source item is rejected."""
import json
import re

from ..config import PROFILE
from ..match.skills import MARKET_SKILLS, find_skills, profile_skills

ALL_SKILLS = sorted(set(profile_skills()) | set(MARKET_SKILLS))
_STOP = set("the and for with from into over under within using via of to in on at by an a as or its their this that these "
            "those was were is are be been being which while across through each such than then also more most".split())
# Common action verbs a rephrase may use even if your profile words it differently.
_GENERIC = set("use used build built tell make made create created enable enabled provide provided ensure ensured deliver "
               "delivered implement implemented design designed develop developed improve improved handle handled".split())
_WEAK = re.compile(r"\b(assist(?:ed|ing)?|help(?:ed|ing)?|participat(?:ed|ing)|contribut(?:ed|ing)\s+to|support(?:ed|ing)|"
                   r"involved\s+in|exposure\s+to|familiar(?:ity)?\s+with|learn(?:ed|t|ing))\b", re.I)


def _stem(word: str) -> str:
    w = word.lower()
    for suffix in ("ing", "ed", "es", "s", "e"):
        if w.endswith(suffix) and len(w) - len(suffix) >= 4:
            return w[: -len(suffix)]
    return w


def content_words(text: str) -> set[str]:
    return {_stem(w) for w in re.findall(r"[A-Za-z][A-Za-z+#]*", text or "") if len(w) >= 4 and w.lower() not in _STOP}


PROFILE_WORDS = content_words(json.dumps(PROFILE)) | {_stem(g) for g in _GENERIC}


def check_meaning(new: str, original: str) -> str | None:
    """A rephrase must keep the original's substance, add no wording absent from your whole profile,
    and never undersell (no "assisted"/"helped" unless the original said so)."""
    orig, new_words = content_words(original), content_words(new)
    if orig and len(orig & new_words) / len(orig) < 0.5:
        return "changes the meaning too much"
    novel = new_words - PROFILE_WORDS
    if novel:
        return f"adds wording that isn't in your profile: {', '.join(sorted(novel))}"
    if _WEAK.search(new) and not _WEAK.search(original):
        return "undersells the original (weaker verb)"
    return None
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
    return check_text(new, item_text(item), max_len=int(len(original) * 1.35) + 30) or check_meaning(new, original)


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
