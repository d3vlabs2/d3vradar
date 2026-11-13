from fastapi.testclient import TestClient

from radar.app import app
from radar.documents import extract
from test_app import HEADERS, JOB
from test_workspaces import FRIEND, tenants


BASE = b"Casey Example\n\nExperience\n- Repaired desktop hardware.\n- Maintained DNS records and Windows systems."
POSTING = {
    **JOB,
    "url": "https://example.test/support-role",
    "description": "Our team needs a support technician to maintain Windows systems, troubleshoot DNS, and support Intune deployments.",
}


def upload(client, headers=None):
    result = client.post(
        "/api/documents", headers=headers, data={"kind": "resume"},
        files={"file": ("base.txt", BASE, "text/plain")},
    )
    assert result.status_code == 200
    return result.json()["id"]


def test_resume_from_import_saves_reviewed_docx_and_selection():
    with TestClient(app, headers=HEADERS) as client:
        base = upload(client)
        preview = client.post("/api/import/resume-preview", json={**POSTING, "document_id": base})
        assert preview.status_code == 200
        draft = preview.json()
        assert "DNS" in draft["report"]["matched"]
        assert "Intune" in draft["report"]["missing"]
        assert "Intune" not in draft["text"]
        text = draft["text"].replace("Maintained DNS records", "Maintained internal DNS records")
        result = client.post("/api/jobs", json={**POSTING, "tailored_resume": {"text": text}})
        assert result.status_code == 200
        job = result.json()["job"]["id"]
        version = result.json()["resumeId"]
        workspace = client.get("/api/workspace").json()
        assert workspace["resumeSelections"][job] == version
        assert next(d for d in workspace["documents"] if d["id"] == base)["active"]
        saved = next(d for d in workspace["documents"] if d["id"] == version)
        assert saved["job_id"] == job and not saved["active"]
        file = client.get(f"/api/documents/{version}/original")
        assert "Maintained internal DNS records" in extract(saved["name"], file.content)

        selection = f"/api/jobs/{job}/resume-selection"
        assert client.put(selection, json={"document_id": base}).status_code == 200
        assert client.put(f"/api/applications/{job}", json={"status": "applied"}).status_code == 200
        assert client.get("/api/workspace").json()["resumeSelections"][job] == base
        assert client.put(selection, json={"document_id": None}).status_code == 200
        assert job not in client.get("/api/workspace").json()["resumeSelections"]

        draft = client.post(f"/api/jobs/{job}/resume-preview", json={"document_id": base})
        assert draft.status_code == 200
        newer = client.post(f"/api/jobs/{job}/resumes", json={"text": draft.json()["text"]})
        assert newer.status_code == 200
        assert newer.json()["id"] != version


def test_invalid_resume_keeps_import_unsaved():
    with TestClient(app, headers=HEADERS) as client:
        payload = {**POSTING, "url": "https://example.test/invalid-resume", "tailored_resume": {"text": " " * 31}}
        assert client.post("/api/jobs", json=payload).status_code == 400
        assert all(job["url"] != payload["url"] for job in client.get("/api/workspace").json()["jobs"])


def test_tailored_resumes_stay_in_their_workspace(tenants):
    client, headers, _ = tenants
    base = upload(client, headers())
    job = client.post("/api/jobs", headers=headers(), json=POSTING).json()["job"]["id"]
    saved = client.post(f"/api/jobs/{job}/resumes", headers=headers(), json={"text": BASE.decode()})
    version = saved.json()["id"]
    friend_headers = headers(FRIEND)
    friend_job = client.post("/api/jobs", headers=friend_headers, json=POSTING).json()["job"]["id"]
    assert client.post("/api/import/resume-preview", headers=friend_headers, json={**POSTING, "document_id": base}).status_code == 404
    assert client.get(f"/api/documents/{version}/original", headers=friend_headers).status_code == 404
    assert client.put(f"/api/jobs/{friend_job}/resume-selection", headers=friend_headers, json={"document_id": version}).status_code == 404
