from fastapi.testclient import TestClient

from app.main import app


def test_spa_cannot_escape_dist():
    with TestClient(app) as client:
        result = client.get('/%2e%2e/%2e%2e/backend/requirements.txt')
        assert result.status_code == 404


def test_unknown_api_does_not_return_spa_html():
    with TestClient(app) as client:
        result = client.get('/api/v1/does-not-exist')
        assert result.status_code == 404
