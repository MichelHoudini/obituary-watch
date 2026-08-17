"""
E2E test fixtures.

Unlike tests/test_main.py (which uses FastAPI's TestClient -- fast, but
never runs real JS or renders anything), these tests spin up an actual
uvicorn process and drive it with a real browser via Playwright. That's
the only way to catch things TestClient structurally can't: broken client-
side JS, a page that 500s only under a real ASGI server, etc.

Deliberately scoped to server-rendered content and navigation only --
nothing here exercises the /watch form's live submission flow, since that
depends on a live client-side call to Wikipedia's API (real external
network dependency, would make CI flaky and sends unwanted bot traffic to
Wikipedia on every CI run). That flow already has coverage via
tests/test_main.py's rate-limit test hitting the endpoint directly.
"""
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def live_server(tmp_path_factory):
    """Runs the real app via uvicorn as a subprocess, in its own temp
    directory (isolated SQLite DB, never touches a real local DB), seeded
    with the catalog so /people and /person/* pages have real data."""
    workdir = tmp_path_factory.mktemp("e2e_server")
    port = _free_port()
    repo_root = Path(__file__).resolve().parent.parent.parent

    seed = subprocess.run(
        [sys.executable, "-m", "app.seed"],
        cwd=workdir,
        env={"PYTHONPATH": str(repo_root)},
        capture_output=True,
        text=True,
    )
    assert seed.returncode == 0, f"seed failed: {seed.stderr}"

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=workdir,
        env={"PYTHONPATH": str(repo_root)},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 15
    ready = False
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                ready = True
                break
        except OSError:
            time.sleep(0.2)

    if not ready:
        proc.terminate()
        output = proc.stdout.read() if proc.stdout else ""
        pytest.fail(f"live_server did not start in time.\n{output}")

    yield base_url

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
