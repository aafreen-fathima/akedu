import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_tmp = tempfile.mkdtemp(prefix="akedu-test-")
os.environ.update({
    "AKEDU_DATABASE_URL": f"sqlite:///{_tmp}/test.db",
    "AKEDU_UPLOAD_DIR": f"{_tmp}/uploads",
    "AKEDU_LLM_PROVIDER": "heuristic",
    "AKEDU_TODAY": "2026-10-01",
    "AKEDU_SEED_DEMO": "false",
})
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def samples(tmp_path_factory):
    from make_sample_outlines import make
    return {p.name: p for p in make(tmp_path_factory.mktemp("samples"))}


@pytest.fixture()
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


_counter = iter(range(10_000))


@pytest.fixture()
def user(client):
    email = f"student{next(_counter)}@test.ca"
    r = client.post("/api/v1/auth/register", json={"email": email, "password": "secret123"})
    assert r.status_code == 200, r.text
    return email
