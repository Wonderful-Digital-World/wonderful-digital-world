"""Launch Command Center and World View as one local operator surface."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen


LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _wait_for(url: str, processes: list[subprocess.Popen[bytes]], timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for process in processes:
            if process.poll() is not None:
                raise RuntimeError(f"A service exited early with status {process.returncode}")
        try:
            with urlopen(url, timeout=1) as response:
                if response.status < 500:
                    return
        except (URLError, TimeoutError, OSError):
            pass
        time.sleep(0.2)
    raise TimeoutError(f"Timed out waiting for {url}")


def _stop(processes: list[subprocess.Popen[bytes]]) -> None:
    for process in processes:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and any(p.poll() is None for p in processes):
        time.sleep(0.1)
    for process in processes:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
    for process in processes:
        process.wait()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--database", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--command-port", type=int, default=8787)
    parser.add_argument("--world-port", type=int, default=3000)
    parser.add_argument("--timeout", type=float, default=60)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    workspace = args.workspace.resolve()
    core = workspace / "wonderful-digital-world"
    world_repository = workspace / "world-view"
    world = world_repository / "website"
    database = (args.database or core / "wdw-command-center.sqlite3").resolve()
    if args.host not in LOOPBACK_HOSTS:
        raise SystemExit("--host must be a loopback host")
    if args.command_port == args.world_port or not all(
        1 <= port <= 65535 for port in (args.command_port, args.world_port)
    ):
        raise SystemExit("Choose two distinct valid ports")
    if not (core / "packages" / "wdw_observability").is_dir() or not (world / "package.json").is_file():
        raise SystemExit(f"Expected the split repositories beneath {workspace}")

    command_url = f"http://{args.host}:{args.command_port}"
    world_url = f"http://{args.host}:{args.world_port}"
    command_env = os.environ.copy()
    command_env["PYTHONPATH"] = os.pathsep.join(
        filter(None, (str(core / "packages"), command_env.get("PYTHONPATH", "")))
    )
    command_env["WDW_WORLD_VIEW_URL"] = f"{world_url}/rooms"
    processes: list[subprocess.Popen[bytes]] = []
    try:
        processes.append(
            subprocess.Popen(
                [sys.executable, "-m", "wdw_observability.app", "--workspace", str(workspace),
                 "--database", str(database), "--host", args.host, "--port", str(args.command_port)],
                cwd=core, env=command_env, start_new_session=True,
            )
        )
        processes.append(
            subprocess.Popen(
                ["pnpm", "--dir", str(world), "exec", "next", "dev", "--webpack",
                 "--hostname", args.host, "--port", str(args.world_port)],
                cwd=world_repository, start_new_session=True,
            )
        )
        _wait_for(f"{command_url}/healthz", processes, args.timeout)
        _wait_for(f"{world_url}/rooms", processes, args.timeout)
        print(f"Command Center: {command_url}", flush=True)
        print(f"World View:     {world_url}/rooms", flush=True)
        while all(process.poll() is None for process in processes):
            time.sleep(0.5)
        return next((process.returncode or 0 for process in processes if process.poll() is not None), 0)
    except KeyboardInterrupt:
        return 0
    finally:
        _stop(processes)


if __name__ == "__main__":
    raise SystemExit(main())
