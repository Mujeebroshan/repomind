from fastapi.testclient import TestClient

from codechat.main import app

client = TestClient(app)


def test_health():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_open_workspace_rejects_bad_path():
    resp = client.post("/api/workspace", json={"repo_path": "/path/does/not/exist"})
    assert resp.status_code == 400


def test_open_workspace_and_settings_roundtrip(tmp_path):
    resp = client.post("/api/workspace", json={"repo_path": str(tmp_path)})
    assert resp.status_code == 200
    body = resp.json()
    assert body["indexed"] is False
    assert "anthropic" in body["settings"]["providers"]

    update = client.post(
        "/api/settings",
        params={"repo_path": str(tmp_path)},
        json={"providers": {"anthropic": {"api_key": "sk-ant-test-123456789", "model": "claude-sonnet-4-6"}}},
    )
    assert update.status_code == 200
    updated = update.json()
    assert updated["providers"]["anthropic"]["configured"] is True
    # key is masked, never echoed back in full
    assert "sk-ant-test" not in updated["providers"]["anthropic"]["api_key_preview"] or updated["providers"]["anthropic"]["api_key_preview"].count("*") > 0


def test_index_status_defaults_to_idle_before_indexing(tmp_path):
    client.post("/api/workspace", json={"repo_path": str(tmp_path)})
    resp = client.get("/api/index/status", params={"repo_path": str(tmp_path)})
    assert resp.status_code == 200
    assert resp.json()["state"] == "idle"
