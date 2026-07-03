from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_codex_agent_skills_link_to_claude_skills() -> None:
    agents_skills = ROOT / ".agents" / "skills"
    claude_skills = ROOT / ".claude" / "skills"

    assert agents_skills.is_symlink()
    assert agents_skills.readlink() == Path("../.claude/skills")
    assert agents_skills.resolve() == claude_skills.resolve()

    claude_skill_names = sorted(path.parent.name for path in claude_skills.glob("*/SKILL.md"))
    agents_skill_names = sorted(path.parent.name for path in agents_skills.glob("*/SKILL.md"))

    assert agents_skill_names == claude_skill_names
    assert agents_skill_names


def test_agent_notes_document_skill_sync_contract() -> None:
    agent_notes = (ROOT / "AGENTS.md").read_text()

    assert "Keep Claude and Codex skill access synchronized at all times." in agent_notes
    assert "`.agents/skills` must point at `.claude/skills`" in agent_notes


def test_claude_md_links_to_agents_md() -> None:
    claude_md = ROOT / "CLAUDE.md"

    assert claude_md.is_symlink()
    assert claude_md.readlink() == Path("AGENTS.md")

    agent_notes = (ROOT / "AGENTS.md").read_text()
    assert "`CLAUDE.md` must be a symlink to `AGENTS.md`" in agent_notes


def test_worktree_bootstrap_script_is_executable() -> None:
    bootstrap = ROOT / "scripts" / "bootstrap-worktree.sh"

    assert bootstrap.is_file()
    assert bootstrap.stat().st_mode & 0o111, "bootstrap-worktree.sh must be executable"
