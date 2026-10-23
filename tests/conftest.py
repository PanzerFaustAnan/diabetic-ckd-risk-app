import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app, ARTIFACT_DIR
from app.model_service import ModelService


@pytest.fixture(scope="session")
def service():
    return ModelService(ARTIFACT_DIR)


@pytest.fixture(scope="session")
def client():
    # the 'with' block runs the app's startup (lifespan), which loads the model
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def examples():
    return json.loads((Path(ARTIFACT_DIR) / "example_requests.json").read_text())
