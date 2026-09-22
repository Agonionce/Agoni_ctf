"""Structured workspace capabilities for safe local autonomous reasoning."""

from __future__ import annotations

import base64
import hashlib
import json
import tarfile
import zipfile
from pathlib import Path
from typing import Any

from agent.tools.contracts import (
    ExecutionContext,
    Tool,
    ToolExecutionOutput,
    ToolMetadata,
    ToolRiskLevel,
)


_READ_SCOPES = ("input", "work", "output")
_WRITE_SCOPES = ("work", "output")
_MAX_TEXT_BYTES = 1_000_000
_MAX_BINARY_READ = 65_536
_MAX_LIST_ENTRIES = 512
_MAX_ARCHIVE_ENTRIES = 1_000
_MAX_ARCHIVE_BYTES = 100_000_000


def _path_schema() -> dict[str, Any]:
    return {
        "type": "string",
        "minLength": 1,
        "description": "Canonical workspace URI, for example workspace://input/file.txt",
    }


def _resolve(
    context: ExecutionContext,
    value: object,
    *,
    allowed_scopes: tuple[str, ...] = _READ_SCOPES,
    default_scope: str = "work",
):
    return context.workspace_path_resolver().resolve(
        str(value),
        allowed_scopes=allowed_scopes,
        default_scope=default_scope,
    )


class WorkspaceListTool(Tool):
    metadata = ToolMetadata(
        name="workspace_list",
        description="List one contained workspace directory without shell execution.",
        risk_level=ToolRiskLevel.LOW,
        requires_network=False,
        writes_files=False,
        execution_type="workspace_read",
        path_argument_names=("path",),
        autonomous_allowed=True,
    )
    input_schema = {
        "type": "object",
        "properties": {"path": _path_schema()},
        "required": ["path"],
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any], context: ExecutionContext) -> ToolExecutionOutput:
        try:
            resolved = _resolve(context, arguments["path"])
            if not resolved.path.is_dir():
                return ToolExecutionOutput(False, error=f"directory not found: {resolved.uri}")
            entries = []
            truncated = False
            for index, child in enumerate(sorted(resolved.path.iterdir(), key=lambda item: item.name)):
                if index >= _MAX_LIST_ENTRIES:
                    truncated = True
                    break
                try:
                    child_uri = context.workspace_path_resolver().uri_for_path(child)
                except ValueError:
                    continue
                stat = child.lstat()
                entries.append(
                    {
                        "name": child.name,
                        "uri": child_uri,
                        "type": (
                            "symlink"
                            if child.is_symlink()
                            else "directory"
                            if child.is_dir()
                            else "file"
                            if child.is_file()
                            else "other"
                        ),
                        "size": stat.st_size,
                    }
                )
            return ToolExecutionOutput(
                True,
                stdout=json.dumps(
                    {"path": resolved.uri, "entries": entries, "truncated": truncated},
                    ensure_ascii=False,
                ),
                metadata={"workspace_uri": resolved.uri, "entry_count": len(entries)},
            )
        except (KeyError, OSError, ValueError) as error:
            return ToolExecutionOutput(False, error=f"workspace list failed: {error}")


class WorkspaceReadTextTool(Tool):
    metadata = ToolMetadata(
        name="workspace_read_text",
        description="Read bounded UTF-8 text from a contained workspace file.",
        risk_level=ToolRiskLevel.LOW,
        requires_network=False,
        writes_files=False,
        execution_type="workspace_read",
        path_argument_names=("path",),
        autonomous_allowed=True,
    )
    input_schema = {
        "type": "object",
        "properties": {"path": _path_schema()},
        "required": ["path"],
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any], context: ExecutionContext) -> ToolExecutionOutput:
        try:
            resolved = _resolve(context, arguments["path"])
            if not resolved.path.is_file():
                return ToolExecutionOutput(False, error=f"file not found: {resolved.uri}")
            size = resolved.path.stat().st_size
            if size > _MAX_TEXT_BYTES:
                return ToolExecutionOutput(False, error="text file exceeds the 1 MB read limit")
            content = resolved.path.read_text(encoding="utf-8")
            return ToolExecutionOutput(
                True,
                stdout=content,
                metadata={"workspace_uri": resolved.uri, "bytes": size, "encoding": "utf-8"},
            )
        except UnicodeDecodeError:
            return ToolExecutionOutput(False, error="file is not valid UTF-8 text")
        except (KeyError, OSError, ValueError) as error:
            return ToolExecutionOutput(False, error=f"workspace text read failed: {error}")


class WorkspaceReadBytesTool(Tool):
    metadata = ToolMetadata(
        name="workspace_read_bytes",
        description="Read a bounded binary fragment and return base64 and hex previews.",
        risk_level=ToolRiskLevel.LOW,
        requires_network=False,
        writes_files=False,
        execution_type="workspace_read",
        path_argument_names=("path",),
        autonomous_allowed=True,
    )
    input_schema = {
        "type": "object",
        "properties": {
            "path": _path_schema(),
            "offset": {"type": "integer", "minimum": 0},
            "length": {"type": "integer", "minimum": 1, "maximum": _MAX_BINARY_READ},
        },
        "required": ["path"],
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any], context: ExecutionContext) -> ToolExecutionOutput:
        try:
            resolved = _resolve(context, arguments["path"])
            if not resolved.path.is_file():
                return ToolExecutionOutput(False, error=f"file not found: {resolved.uri}")
            offset = int(arguments.get("offset", 0))
            length = int(arguments.get("length", 4096))
            with resolved.path.open("rb") as file:
                file.seek(offset)
                data = file.read(length)
            payload = {
                "path": resolved.uri,
                "offset": offset,
                "bytes_read": len(data),
                "base64": base64.b64encode(data).decode("ascii"),
                "hex_preview": data[:256].hex(),
            }
            return ToolExecutionOutput(
                True,
                stdout=json.dumps(payload, ensure_ascii=False),
                metadata={"workspace_uri": resolved.uri, "bytes_read": len(data)},
            )
        except (KeyError, OSError, ValueError) as error:
            return ToolExecutionOutput(False, error=f"workspace binary read failed: {error}")


class WorkspaceWriteTextTool(Tool):
    metadata = ToolMetadata(
        name="workspace_write_text",
        description="Write bounded UTF-8 text under workspace work or output scope.",
        risk_level=ToolRiskLevel.MEDIUM,
        requires_network=False,
        writes_files=True,
        execution_type="workspace_write",
        path_argument_names=("path",),
        path_scope_rules=(("path", _WRITE_SCOPES),),
        autonomous_allowed=True,
    )
    input_schema = {
        "type": "object",
        "properties": {
            "path": _path_schema(),
            "content": {"type": "string", "maxLength": _MAX_TEXT_BYTES},
            "overwrite": {"type": "boolean"},
        },
        "required": ["path", "content"],
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any], context: ExecutionContext) -> ToolExecutionOutput:
        try:
            resolved = _resolve(
                context,
                arguments["path"],
                allowed_scopes=_WRITE_SCOPES,
            )
            content = str(arguments["content"])
            if len(content.encode("utf-8")) > _MAX_TEXT_BYTES:
                return ToolExecutionOutput(False, error="text content exceeds the 1 MB write limit")
            if resolved.path.exists() and not bool(arguments.get("overwrite", False)):
                return ToolExecutionOutput(False, error=f"file already exists: {resolved.uri}")
            resolved.path.parent.mkdir(parents=True, exist_ok=True)
            resolved.path.write_text(content, encoding="utf-8")
            return ToolExecutionOutput(
                True,
                stdout=json.dumps({"path": resolved.uri, "bytes": len(content.encode('utf-8'))}),
                artifact_paths=[resolved.path],
                artifact_type="text",
                metadata={"workspace_uri": resolved.uri},
            )
        except (KeyError, OSError, ValueError) as error:
            return ToolExecutionOutput(False, error=f"workspace text write failed: {error}")


class FileHashTool(Tool):
    metadata = ToolMetadata(
        name="file_hash",
        description="Calculate a SHA-256 hash for one contained workspace file.",
        risk_level=ToolRiskLevel.LOW,
        requires_network=False,
        writes_files=False,
        execution_type="workspace_read",
        path_argument_names=("path",),
        autonomous_allowed=True,
    )
    input_schema = {
        "type": "object",
        "properties": {"path": _path_schema()},
        "required": ["path"],
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any], context: ExecutionContext) -> ToolExecutionOutput:
        try:
            resolved = _resolve(context, arguments["path"])
            if not resolved.path.is_file():
                return ToolExecutionOutput(False, error=f"file not found: {resolved.uri}")
            digest = hashlib.sha256()
            with resolved.path.open("rb") as file:
                for chunk in iter(lambda: file.read(65_536), b""):
                    digest.update(chunk)
            payload = {"path": resolved.uri, "algorithm": "sha256", "digest": digest.hexdigest()}
            return ToolExecutionOutput(True, stdout=json.dumps(payload), metadata=payload)
        except (KeyError, OSError, ValueError) as error:
            return ToolExecutionOutput(False, error=f"file hash failed: {error}")


class ArchiveListTool(Tool):
    metadata = ToolMetadata(
        name="archive_list",
        description="List ZIP or TAR members without extracting or executing content.",
        risk_level=ToolRiskLevel.LOW,
        requires_network=False,
        writes_files=False,
        execution_type="archive_metadata",
        path_argument_names=("path",),
        autonomous_allowed=True,
    )
    input_schema = {
        "type": "object",
        "properties": {"path": _path_schema()},
        "required": ["path"],
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any], context: ExecutionContext) -> ToolExecutionOutput:
        try:
            resolved = _resolve(context, arguments["path"])
            if not resolved.path.is_file():
                return ToolExecutionOutput(False, error=f"archive not found: {resolved.uri}")
            if resolved.path.stat().st_size > _MAX_ARCHIVE_BYTES:
                return ToolExecutionOutput(False, error="archive exceeds the 100 MB inspection limit")
            if zipfile.is_zipfile(resolved.path):
                archive_type = "zip"
                with zipfile.ZipFile(resolved.path) as archive:
                    raw_entries = archive.infolist()
                    entries = [
                        {"name": item.filename, "size": item.file_size, "is_dir": item.is_dir()}
                        for item in raw_entries[:_MAX_ARCHIVE_ENTRIES]
                    ]
            elif tarfile.is_tarfile(resolved.path):
                archive_type = "tar"
                with tarfile.open(resolved.path, mode="r:*") as archive:
                    raw_entries = archive.getmembers()
                    entries = [
                        {"name": item.name, "size": item.size, "is_dir": item.isdir()}
                        for item in raw_entries[:_MAX_ARCHIVE_ENTRIES]
                    ]
            else:
                return ToolExecutionOutput(False, error="unsupported archive format")
            payload = {
                "path": resolved.uri,
                "archive_type": archive_type,
                "entries": entries,
                "truncated": len(raw_entries) > _MAX_ARCHIVE_ENTRIES,
            }
            return ToolExecutionOutput(
                True,
                stdout=json.dumps(payload, ensure_ascii=False),
                metadata={"workspace_uri": resolved.uri, "archive_type": archive_type},
            )
        except (KeyError, OSError, ValueError, tarfile.TarError, zipfile.BadZipFile) as error:
            return ToolExecutionOutput(False, error=f"archive list failed: {error}")
