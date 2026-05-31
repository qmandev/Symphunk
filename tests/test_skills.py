import pytest
import symphunk.harness.skills as skills_module
from symphunk.harness.skills import load, load_all, SkillNotFound


def test_load_existing_skill(tmp_path, monkeypatch):
    skill_dir = tmp_path / "obs"
    skill_dir.mkdir()
    (skill_dir / "test-skill.md").write_text("# Test\nContent here")
    monkeypatch.setattr(skills_module, "_SKILLS_ROOT", tmp_path)
    content = load("test-skill", domain="obs")
    assert "Content here" in content


def test_load_missing_skill_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(skills_module, "_SKILLS_ROOT", tmp_path)
    with pytest.raises(SkillNotFound):
        load("nonexistent", domain="obs")


def test_load_all_returns_all_skills(tmp_path, monkeypatch):
    skill_dir = tmp_path / "obs"
    skill_dir.mkdir()
    (skill_dir / "skill-a.md").write_text("Skill A")
    (skill_dir / "skill-b.md").write_text("Skill B")
    monkeypatch.setattr(skills_module, "_SKILLS_ROOT", tmp_path)
    result = load_all("obs")
    assert set(result.keys()) == {"skill-a", "skill-b"}


def test_load_all_empty_domain(tmp_path, monkeypatch):
    monkeypatch.setattr(skills_module, "_SKILLS_ROOT", tmp_path)
    assert load_all("nonexistent") == {}
