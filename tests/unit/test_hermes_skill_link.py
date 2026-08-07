import os
import subprocess
from pathlib import Path

SCRIPT = (
    Path(__file__).parents[2] / "integrations" / "hermes" / "scripts" / "link-gym-coach-skill.sh"
)
SOURCE_SKILL = (
    Path(__file__).parents[2] / "integrations" / "hermes" / "skills" / "gym-coach" / "SKILL.md"
)


def _run(script_arg: str, hermes_home: Path) -> subprocess.CompletedProcess[str]:
    environment = {**os.environ, "HERMES_HOME": str(hermes_home)}
    return subprocess.run(
        ["bash", str(SCRIPT), script_arg],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def test_skill_link_installer_backs_up_and_is_idempotent(tmp_path: Path) -> None:
    hermes_home = tmp_path / "hermes"
    target = hermes_home / "skills" / "health" / "gym-coach" / "SKILL.md"
    target.parent.mkdir(parents=True)
    target.write_text("old skill\n", encoding="utf-8")

    installed = _run("--link", hermes_home)
    checked = _run("--check", hermes_home)
    repeated = _run("--link", hermes_home)

    assert installed.returncode == 0
    assert checked.returncode == 0
    assert repeated.returncode == 0
    assert target.is_symlink()
    assert target.resolve() == SOURCE_SKILL.resolve()
    backups = list(target.parent.glob("SKILL.md.backup.*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "old skill\n"
