"""Bounded temporary upload staging for the local Presentation Layer."""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import UploadFile

from agent.challenge.validator import reject_sensitive_path
from webui.service import UISettings


class UploadValidationError(ValueError):
    pass


class UploadSession:
    """Stage browser files beneath a temporary local root and clean on exit."""

    CHUNK_SIZE = 64 * 1024

    def __init__(self, settings: UISettings) -> None:
        self.settings = settings
        self._temporary: tempfile.TemporaryDirectory[str] | None = None
        self.root = Path()
        self.total_bytes = 0
        self.file_count = 0

    def __enter__(self) -> "UploadSession":
        self.settings.staging_root.mkdir(parents=True, exist_ok=True)
        self._temporary = tempfile.TemporaryDirectory(
            prefix="challenge-",
            dir=self.settings.staging_root,
        )
        self.root = Path(self._temporary.name).resolve()
        return self

    def __exit__(self, *_args: object) -> None:
        if self._temporary is not None:
            self._temporary.cleanup()

    async def stage_many(
        self,
        uploads: list[UploadFile],
        *,
        group: str,
    ) -> list[Path]:
        staged: list[Path] = []
        for upload in uploads:
            staged.append(await self.stage(upload, group=group))
        return staged

    async def stage(self, upload: UploadFile, *, group: str) -> Path:
        self.file_count += 1
        if self.file_count > self.settings.max_uploads:
            raise UploadValidationError("上传文件数量过多")
        filename = self._filename(upload.filename)
        reject_sensitive_path(Path(filename))
        directory = self.root / group
        directory.mkdir(parents=True, exist_ok=True)
        destination = (directory / filename).resolve()
        try:
            destination.relative_to(directory.resolve())
        except ValueError as error:
            raise UploadValidationError("文件名不安全") from error
        if destination.exists():
            raise UploadValidationError(f"存在重复文件名：{filename}")
        file_bytes = 0
        try:
            with destination.open("wb") as target:
                while True:
                    chunk = await upload.read(self.CHUNK_SIZE)
                    if not chunk:
                        break
                    file_bytes += len(chunk)
                    self.total_bytes += len(chunk)
                    if file_bytes > self.settings.max_file_bytes:
                        raise UploadValidationError(f"文件过大：{filename}")
                    if self.total_bytes > self.settings.max_total_bytes:
                        raise UploadValidationError("本次上传总大小超过限制")
                    target.write(chunk)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        finally:
            await upload.close()
        return destination.relative_to(self.root)

    @staticmethod
    def _filename(value: str | None) -> str:
        filename = (value or "").strip()
        if (
            not filename
            or len(filename) > 255
            or "\x00" in filename
            or "/" in filename
            or "\\" in filename
            or filename in {".", ".."}
        ):
            raise UploadValidationError("文件名不安全")
        return filename
