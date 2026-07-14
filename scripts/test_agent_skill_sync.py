from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / ".claude" / "skills"


def _skill_text(name: str) -> str:
    return (SKILLS / name / "SKILL.md").read_text()


def _assert_contains_all(text: str, required: tuple[str, ...]) -> None:
    missing = [value for value in required if value not in text]
    assert not missing, f"missing required skill guidance: {missing}"


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


def test_agent_delivery_contract_covers_pressure_scenarios() -> None:
    text = _skill_text("agent-delivery-contract")

    _assert_contains_all(
        text,
        (
            "Use when",
            "Authority",
            "Terminal state",
            "Failure policy",
            "proportional verification",
            "required checks",
            "state transitions",
            "unchanged polling",
            "fresh evidence",
            "infrastructure",
        ),
    )


def test_repair_pr_handles_rebase_ci_and_merge_pressure() -> None:
    text = _skill_text("repair-pr")

    _assert_contains_all(
        text,
        (
            "Use when",
            "agent-delivery-contract",
            "--force-with-lease",
            "caused by the PR",
            "required checks",
            "merge queue",
            "infrastructure",
            "mergedAt",
        ),
    )


def test_tdd_ship_requires_the_shared_delivery_contract() -> None:
    text = _skill_text("tdd-ship")

    assert "**REQUIRED SUB-SKILL:** Use agent-delivery-contract" in text


def test_orchestrate_prs_avoids_stale_ci_and_conflicting_merges() -> None:
    text = _skill_text("orchestrate-prs")

    _assert_contains_all(
        text,
        (
            "Use when",
            "agent-delivery-contract",
            "repair-pr",
            "overlapping files",
            "serialize",
            "bounded concurrency",
            "Re-evaluate",
            "status table",
            "origin/main",
        ),
    )
