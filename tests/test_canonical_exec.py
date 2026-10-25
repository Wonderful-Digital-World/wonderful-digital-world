import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "ops" / "canonical-exec"


def checkout(root: Path) -> tuple[Path, str]:
    repo = root / "service"
    repo.mkdir()
    git = ["git", "-C", str(repo), "-c", "user.email=t@example.com", "-c", "user.name=t"]
    subprocess.run(git[:3] + ["init", "-q"], check=True)
    (repo / "app.txt").write_text("v1")
    subprocess.run(git + ["add", "."], check=True)
    subprocess.run(git + ["commit", "-qm", "v1"], check=True)
    sha = subprocess.run(git[:3] + ["rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    return repo, sha


def run(root: Path, repo: Path, sha: str, env_file: str = "-", *command: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "WDW_WORKSPACE_ROOT": str(root), "WDW_RUNTIME_STATE_ROOT": str(root / "state")}
    return subprocess.run([str(SCRIPT), "demo", str(repo), sha, str(repo), env_file, *(command or ("cat", "app.txt"))],
                          capture_output=True, text=True, env=env)


def test_runs_only_at_the_pinned_commit_and_records_provenance(tmp_path):
    repo, sha = checkout(tmp_path)
    ok = run(tmp_path, repo, sha)
    assert ok.returncode == 0 and ok.stdout == "v1"
    assert f"commit={sha}" in (tmp_path / "state/provenance/demo.env").read_text()
    moved = run(tmp_path, repo, "0" * 40)
    assert moved.returncode == 78 and "canonical commit mismatch" in moved.stderr


def test_env_file_values_are_data_not_shell(tmp_path):
    repo, sha = checkout(tmp_path)
    env_file = tmp_path / "service.env"
    env_file.write_text('GREETING="$(touch pwned) hello"\n')
    result = run(tmp_path, repo, sha, str(env_file), "sh", "-c", 'printf %s "$GREETING"')
    assert result.stdout == "$(touch pwned) hello" and not (repo / "pwned").exists()
