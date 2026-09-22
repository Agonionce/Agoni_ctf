from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from webui.app import create_app
from webui.service import UISettings


LOCAL_ORIGIN = {"origin": "http://127.0.0.1:5173"}


def _client(tmp_path: Path, *, max_file_bytes: int = 1024 * 1024) -> TestClient:
    return TestClient(
        create_app(
            UISettings(
                workspace_root=tmp_path / "workspace",
                experience_root=tmp_path / "experiences" / "challenges",
                staging_root=tmp_path / "staging",
                max_file_bytes=max_file_bytes,
                max_total_bytes=max_file_bytes * 4,
                max_uploads=8,
            )
        )
    )


def _create(client: TestClient, *, name: str = "local_web"):
    return client.post(
        "/api/challenges",
        data={
            "name": name,
            "description": "# 本地题目\n\n只分析已授权的测试材料。",
            "domain": "web",
            "target_url": "http://127.0.0.1:5000",
            "authorization_confirmed": "true",
        },
        files=[
            ("attachments", ("challenge.txt", b"fake attachment", "text/plain")),
            ("source_files", ("app.py", b"print('fake local')\n", "text/x-python")),
        ],
        headers=LOCAL_ORIGIN,
    )


def test_r14_health_catalog_create_and_detail_are_challenge_safe(tmp_path):
    client = _client(tmp_path)

    assert client.get("/api/health").json() == {
        "status": "ok",
        "service": "agonionce-local-ui",
    }
    assert client.get("/api/challenges").json() == {"items": []}

    created = _create(client)

    assert created.status_code == 201, created.text
    detail = created.json()
    assert detail["name"] == "local_web"
    assert detail["domain"] == "web"
    assert detail["status"] == "not_started"
    assert detail["status_label"] == "未开始"
    assert detail["target_url"] == "http://127.0.0.1:5000"
    assert detail["materials"] == [
        {"name": "input/challenge.txt", "kind": "attachment"},
        {"name": "input/source/app.py", "kind": "source"},
    ]
    assert str(tmp_path) not in created.text
    assert "workspace" not in created.text

    challenge_id = detail["challenge_id"]
    catalog = client.get("/api/challenges")
    loaded = client.get(f"/api/challenges/{challenge_id}")
    assert catalog.status_code == 200
    assert catalog.json()["items"][0]["name"] == "local_web"
    assert loaded.status_code == 200
    assert loaded.json() == detail

    assert (tmp_path / "workspace" / challenge_id / "input" / "challenge.txt").is_file()
    assert (tmp_path / "workspace" / challenge_id / "input" / "source" / "app.py").is_file()
    assert list((tmp_path / "staging").iterdir()) == []


def test_r14_create_requires_explicit_authorization(tmp_path):
    client = _client(tmp_path)

    result = client.post(
        "/api/challenges",
        data={
            "name": "missing_scope",
            "description": "Authorized text was not confirmed in the UI.",
            "domain": "misc",
            "authorization_confirmed": "false",
        },
        headers=LOCAL_ORIGIN,
    )

    assert result.status_code == 400
    assert result.json()["code"] == "authorization_required"
    assert client.get("/api/challenges").json() == {"items": []}


def test_r14_duplicate_name_points_to_existing_challenge(tmp_path):
    client = _client(tmp_path)
    first = _create(client, name="same challenge")

    duplicate = _create(client, name="same   challenge")

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "duplicate_challenge"
    assert duplicate.json()["existing_challenge_id"] == first.json()["challenge_id"]
    assert len(client.get("/api/challenges").json()["items"]) == 1


def test_r14_preserves_unicode_name_and_detects_normalized_duplicate(tmp_path):
    client = _client(tmp_path)

    created = _create(client, name="旧站备份")
    duplicate = _create(client, name="  旧站备份  ")

    assert created.status_code == 201, created.text
    assert created.json()["name"] == "旧站备份"
    assert created.json()["challenge_id"].startswith("challenge-")
    assert duplicate.status_code == 409
    assert duplicate.json()["existing_challenge_id"] == created.json()["challenge_id"]


def test_r14_rejects_sensitive_and_path_like_upload_names(tmp_path):
    client = _client(tmp_path)
    base = {
        "name": "unsafe_upload",
        "description": "Authorized local fixture.",
        "domain": "misc",
        "authorization_confirmed": "true",
    }

    sensitive = client.post(
        "/api/challenges",
        data=base,
        files=[("attachments", (".env", b"PRIVATE=example", "text/plain"))],
        headers=LOCAL_ORIGIN,
    )
    path_like = client.post(
        "/api/challenges",
        data={**base, "name": "unsafe_path"},
        files=[("attachments", ("../outside.txt", b"outside", "text/plain"))],
        headers=LOCAL_ORIGIN,
    )

    assert sensitive.status_code == 400
    assert sensitive.json()["code"] == "challenge_rejected"
    assert sensitive.json()["message"] == "该文件可能包含敏感信息，请移除后重试"
    assert "refusing" not in sensitive.text
    assert path_like.status_code == 400
    assert path_like.json()["code"] == "upload_rejected"
    assert client.get("/api/challenges").json() == {"items": []}


def test_r14_rejects_oversized_upload_without_partial_intake(tmp_path):
    client = _client(tmp_path, max_file_bytes=4)

    result = client.post(
        "/api/challenges",
        data={
            "name": "too_large",
            "description": "Authorized local fixture.",
            "domain": "misc",
            "authorization_confirmed": "true",
        },
        files=[("attachments", ("large.bin", b"12345", "application/octet-stream"))],
        headers=LOCAL_ORIGIN,
    )

    assert result.status_code == 400
    assert result.json()["code"] == "upload_rejected"
    assert client.get("/api/challenges").json() == {"items": []}
    assert not (tmp_path / "workspace").exists()


def test_r14_rejects_non_local_browser_origin(tmp_path):
    client = _client(tmp_path)

    result = client.post(
        "/api/challenges",
        data={
            "name": "remote_origin",
            "description": "Authorized local fixture.",
            "domain": "misc",
            "authorization_confirmed": "true",
        },
        headers={"origin": "https://example.invalid"},
    )

    assert result.status_code == 403
    assert result.json()["code"] == "origin_denied"
    assert client.get("/api/challenges").json() == {"items": []}


def test_r14_invalid_target_is_presented_without_internal_paths(tmp_path):
    client = _client(tmp_path)

    result = client.post(
        "/api/challenges",
        data={
            "name": "invalid_target",
            "description": "Authorized local fixture.",
            "domain": "web",
            "target_url": "localhost:5000",
            "authorization_confirmed": "true",
        },
        headers=LOCAL_ORIGIN,
    )

    assert result.status_code == 400
    assert result.json()["message"] == "目标地址需要是完整的 HTTP(S) 地址"
    assert str(tmp_path) not in result.text


def test_r14_rejects_sensitive_manifest_text_before_creating_transport_id(tmp_path):
    client = _client(tmp_path)
    result = client.post(
        "/api/challenges",
        data={
            "name": "Authorization: opaquecredential123456",
            "description": "The answer may be HTB{candidate-value}.",
            "domain": "web",
            "target_url": "http://HTB{candidate-value}.example:5000/path?token=private",
            "authorization_confirmed": "true",
        },
        headers=LOCAL_ORIGIN,
    )

    assert result.status_code == 400
    assert result.json()["code"] == "challenge_rejected"
    assert "opaquecredential123456" not in result.text
    assert "candidate-value" not in result.text
    generic_flag = client.post(
        "/api/challenges",
        data={
            "name": "XYZ{candidate-value}",
            "description": "Authorized local fixture.",
            "domain": "web",
            "authorization_confirmed": "true",
        },
        headers=LOCAL_ORIGIN,
    )
    assert generic_flag.status_code == 400
    assert "candidate-value" not in generic_flag.text
    assert client.get("/api/challenges").json() == {"items": []}


def test_r14_target_projection_shows_full_target(tmp_path):
    client = _client(tmp_path)
    created = client.post(
        "/api/challenges",
        data={
            "name": "safe_target_projection",
            "description": "Authorized local fixture.",
            "domain": "web",
            "target_url": "http://127.0.0.1:5000/path?page=1",
            "authorization_confirmed": "true",
        },
        headers=LOCAL_ORIGIN,
    )

    assert created.status_code == 201, created.text
    assert created.json()["target_url"] == "http://127.0.0.1:5000/path?page=1"
    assert "/path" in created.text
    assert "page=1" in created.text
