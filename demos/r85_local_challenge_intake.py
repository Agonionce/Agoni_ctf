"""Deterministic fake-local R8.5 Challenge Intake demonstration."""

from __future__ import annotations

from tempfile import TemporaryDirectory
from pathlib import Path
from zipfile import ZipFile

from agent.challenge.importer import ChallengeImporter


def main() -> None:
    with TemporaryDirectory(prefix="agonionce-r85-") as temporary:
        root = Path(temporary)
        intake = root / "intake"
        source = intake / "fake-source"
        source.mkdir(parents=True)
        (source / "app.py").write_text(
            "print('fake local challenge')\n",
            encoding="utf-8",
        )
        archive = intake / "fake-challenge.zip"
        with ZipFile(archive, "w") as package:
            package.writestr("README.txt", "fake local archive")

        result = ChallengeImporter(
            workspace_root=root / "workspace",
            experience_root=root / "experiences" / "challenges",
            source_root=intake,
        ).import_challenge(
            name="fake_web_challenge",
            domain="web",
            description="Authorized fake local Web challenge for intake validation.",
            target_url="http://127.0.0.1:5000",
            attachments=[archive],
            source_paths=[source],
            authorization_scope="authorized_local_demo",
            created_at="2026-08-21T00:00:00+00:00",
            entropy="r85-local-demo",
        )

        assert result.workspace.workspace.input_dir.is_dir()
        assert (result.workspace.workspace.input_dir / archive.name).is_file()
        assert (
            result.workspace.workspace.input_dir
            / "source"
            / "app.py"
        ).is_file()
        assert result.experience.challenge_file.is_file()
        assert result.experience.writeup_file.is_file()
        assert "## Evidence" in result.experience.writeup_file.read_text(
            encoding="utf-8"
        )
        print("LOCAL_CHALLENGE_INTAKE_OK")


if __name__ == "__main__":
    main()
