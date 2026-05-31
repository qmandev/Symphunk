import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_SKILLS_ROOT = Path(__file__).parent.parent.parent / "skills"


def load(name: str, domain: str = "obs") -> str:
    path = _SKILLS_ROOT / domain / f"{name}.md"
    if not path.exists():
        raise SkillNotFound(f"Skill '{domain}/{name}' not found at {path}")
    content = path.read_text(encoding="utf-8")
    logger.debug("Loaded skill %s/%s (%d chars)", domain, name, len(content))
    return content


def load_all(domain: str = "obs") -> dict[str, str]:
    skill_dir = _SKILLS_ROOT / domain
    if not skill_dir.exists():
        return {}
    return {
        p.stem: p.read_text(encoding="utf-8")
        for p in sorted(skill_dir.glob("*.md"))
    }


class SkillNotFound(Exception):
    pass
