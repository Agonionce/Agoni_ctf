"""Deterministic fake-local R14.1 Presentation Layer demonstration."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from webui.app import create_app
from webui.service import UISettings


def main() -> None:
    """Create and review one fake challenge without opening a network target."""

    with TemporaryDirectory(prefix="agonionce-r14-") as temporary:
        root = Path(temporary)
        client = TestClient(
            create_app(
                UISettings(
                    workspace_root=root / "workspace",
                    experience_root=root / "experiences" / "challenges",
                    staging_root=root / "staging",
                )
            )
        )
        created = client.post(
            "/api/challenges",
            data={
                "name": "fake_local_web",
                "description": "# 本地演示\n\n仅导入已授权的假题目材料。",
                "domain": "web",
                "authorization_confirmed": "true",
            },
            files=[
                (
                    "attachments",
                    ("challenge.txt", b"fake local attachment", "text/plain"),
                )
            ],
            headers={"origin": "http://127.0.0.1:8787"},
        )
        assert created.status_code == 201, created.text
        detail = created.json()
        assert detail["status_label"] == "未开始"
        assert detail["materials"] == [
            {"name": "input/challenge.txt", "kind": "attachment"}
        ]
        loaded = client.get(f"/api/challenges/{detail['challenge_id']}")
        assert loaded.status_code == 200
        assert loaded.json() == detail
        assert str(root) not in loaded.text
        print("LOCAL_UI_WORKBENCH_OK")


if __name__ == "__main__":
    main()
