import os
import tempfile

import pytest

os.environ["CLE_PRIVEE_FICHIER"] = os.path.join(tempfile.mkdtemp(), "cle.pem")
os.environ["SERVICE_TOKEN"] = "jeton-de-test"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


SERVICE = {"X-Service-Token": "jeton-de-test"}
