from fastapi.testclient import TestClient

from app.main import app
from app.sample_data import samples

client = TestClient(app)
H = {"X-API-Key": "test-key"}


def test_health_open():
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["storage"] == "memory"


def test_auth_required():
    body = samples()[0]["request"]
    assert client.post("/api/profile", json=body).status_code == 401
    assert client.post("/api/profile", json=body, headers={"X-API-Key": "nope"}).status_code == 401
    assert client.get("/api/profiles").status_code == 401


def test_server_without_configured_key_refuses(monkeypatch):
    monkeypatch.delenv("APP_API_KEY")
    assert client.post("/api/profile", json=samples()[0]["request"], headers=H).status_code == 503


def test_standard_sample_end_to_end():
    r = client.post("/api/profile", json=samples()[0]["request"], headers=H)
    assert r.status_code == 200
    d = r.json()
    assert d["career_entries"] == 3
    assert "Expert Code:" in d["html"] and "EX-100234" in d["html"] and "Current:" in d["html"]
    assert "Q1." in d["html"] and "Former:" in d["html"]
    assert d["availability_kst"].count("KST") == 2
    assert any("template comment" in w for w in d["warnings"])  # no LLM key in tests


def test_clearance_sample_shows_clearance_above_expert_id():
    d = client.post("/api/profile", json=samples()[1]["request"], headers=H).json()
    html = d["html"]
    assert "Clearance:" in html and "Current:" not in html
    assert html.index("Clearance:") < html.index("Expert ID:")
    assert "Q1." not in html and ">1. " in html  # clearance style numbers VQs without a prefix


def test_validation_and_history():
    assert client.post("/api/profile", json={"target_company": ""}, headers=H).status_code == 422
    client.post("/api/profile", json=samples()[0]["request"], headers=H)
    hist = client.get("/api/profiles", headers=H).json()
    assert hist and "html" not in hist[0] and hist[0]["target_company"] == "Helio Dynamics"


def test_unrecognised_career_still_returns_profile():
    body = {**samples()[0]["request"], "career_text": "no structure at all"}
    d = client.post("/api/profile", json=body, headers=H).json()
    assert d["career_entries"] == 0 and any("not recognised" in w for w in d["warnings"])


def test_index_served():
    r = client.get("/")
    assert r.status_code == 200 and "Expert Profile Builder" in r.text
