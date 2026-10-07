from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    # given: 기동된 앱
    # when
    res = client.get("/health")

    # then
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_unknown_path_returns_404(client: TestClient) -> None:
    # given / when
    res = client.get("/nope")

    # then
    assert res.status_code == 404
