import re
from functools import lru_cache

from ..config import PROFILE

# Skills often asked for in JDs that aren't in the profile; used to report gaps.
MARKET_SKILLS = [
    "Java", "Go", "Golang", "Rust", "Kotlin", "Swift", "C", "C#", "Bash", "Scala", "Ruby", "PHP",
    "React", "Next.js", "Node.js", "Angular", "Vue", "Django", "Spring", "Express", "GraphQL", "gRPC",
    "Kubernetes", "Terraform", "GCP", "Azure", "CI/CD", "Microservices", "Distributed Systems",
    "Kafka", "Redis", "MongoDB", "MySQL", "Elasticsearch", "Spark", "Airflow", "Hadoop", "Snowflake",
    "PyTorch", "TensorFlow", "scikit-learn", "Pandas", "NumPy", "Computer Vision", "Deep Learning",
    "Penetration Testing", "SIEM", "Splunk", "Cloud Security", "Android", "iOS",
]

ALIASES = {
    "PostgreSQL": ["postgres"], "Machine Learning": ["ml"], "JavaScript": ["js"], "TypeScript": ["ts"],
    "GenAI": ["generative ai", "gen ai"], "LLM": ["llms", "large language model"], "Go": ["golang"],
    "Kubernetes": ["k8s"], "AWS": ["amazon web services"], "Network Security": ["network defense"],
    "Cryptography": ["crypto engineering", "encryption"], "Linux": ["unix"], "REST APIs": ["rest", "restful"],
    "Data Structures": ["dsa"], "NLP": ["natural language processing"],
}


def profile_skills() -> list[str]:
    return [s for group in PROFILE["skills"].values() for s in group]


def _pattern(term: str) -> re.Pattern:
    names = [term, *ALIASES.get(term, [])]
    alt = "|".join(re.escape(n.lower()) for n in names)
    return re.compile(rf"(?<![a-z0-9+#.])(?:{alt})(?![a-z0-9+#])")


@lru_cache(maxsize=None)
def _compiled(term: str) -> re.Pattern:
    return _pattern(term)


def find_skills(text: str, vocab) -> set[str]:
    low = (text or "").lower()
    return {s for s in vocab if _compiled(s).search(low)}


def skill_gap(jd_text: str) -> tuple[list[str], list[str]]:
    """(skills you have that the JD mentions, skills the JD mentions that you lack)."""
    mine = profile_skills()
    have = find_skills(jd_text, mine)
    missing = find_skills(jd_text, [s for s in MARKET_SKILLS if s not in mine])
    # "Go" alone is too ambiguous in prose ("go above and beyond"); only count it via "golang".
    if "Go" in missing and "golang" not in (jd_text or "").lower():
        missing.discard("Go")
    return sorted(have), sorted(missing)
