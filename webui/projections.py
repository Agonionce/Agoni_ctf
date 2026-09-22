"""Read-only R14 outcome and completion projections for the local operator."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

from agent.challenge.experience import ChallengeExperienceManager
from agent.challenge.results import ChallengeFlagResultResolver
from agent.completion.experience import (
    ExperienceCandidateCatalog,
    ExperienceCandidateStore,
)
from agent.completion.models import ExperienceCandidate
from agent.domains.web.state import WebRuntimeState
from agent.intelligence.models import IntelligenceState
from webui.models import (
    ArtifactOutcome,
    ChallengeDocuments,
    ChallengeOutcomes,
    ExperienceCandidateCollection,
    ExperienceCandidateView,
    FlagOutcomeView,
    OutcomeRecord,
    WebEndpointOutcome,
    WebOutcome,
)
from webui.service import UISettings
from webui.safety import repeatedly_unquote


_STATUS_LABELS = {
    "OPEN": "待验证",
    "SUPPORTED": "证据支持",
    "REJECTED": "已排除",
    "CONFIRMED": "已确认",
    "PROPOSED": "待执行",
    "RUNNING": "进行中",
    "SUCCESS": "符合预期",
    "FAILED": "未符合预期",
}

_CONFIDENCE_LABELS = {
    "LOW": "低置信度",
    "MEDIUM": "中等置信度",
    "HIGH": "高置信度",
    "CONFIRMED": "已确认",
}

_CATEGORY_LABELS = {
    "sql_injection": "数据库交互",
    "authentication": "认证行为",
    "authorization_analysis": "访问控制",
    "parameter_behavior": "参数行为",
    "file_processing": "文件处理",
    "parser_behavior": "解析行为",
    "business_logic": "业务状态",
    "web_failed_experiment": "未奏效的 Web 路径",
    "binary_analysis": "二进制分析",
    "crypto_pattern": "密码结构",
}

_KIND_LABELS = {
    "SUCCESSFUL_STRATEGY": "有效策略",
    "FAILED_STRATEGY": "失败经验",
    "GENERAL_INSIGHT": "通用认识",
}

_REVIEW_LABELS = {
    "PENDING": "待审核",
    "APPROVED": "已纳入经验",
    "REJECTED": "已忽略",
}


class ChallengeProjectionService:
    """Project persisted state without mutating Intelligence or Completion."""

    def __init__(self, settings: UISettings) -> None:
        self.settings = settings.normalized()
        self.manager = ChallengeExperienceManager(self.settings.experience_root)

    def outcomes(self, challenge_id: str) -> ChallengeOutcomes:
        manifest = self._manifest(challenge_id)
        paths = self.manager.paths_for(manifest)
        state = self._intelligence(paths.intelligence_file, challenge_id)
        artifacts = self._artifacts(manifest)
        artifact_paths = {
            item.artifact_id: item.path
            for item in artifacts
            if item.artifact_id and item.path
        }
        facts = [
            OutcomeRecord(
                title=self._safe_text(item.category),
                detail=self._safe_text(item.content),
                status_label="已记录事实",
                certainty_label=self._confidence(item.confidence),
                occurred_at=item.created_at,
                artifact_paths=self._paths_for_refs(item.artifact_refs, artifact_paths),
            )
            for item in state.facts
        ]
        findings = [
            OutcomeRecord(
                title=self._safe_text(item.title),
                detail=self._safe_text(item.description),
                status_label="重要发现",
                certainty_label={"HIGH": "高重要性", "MEDIUM": "中等重要性", "LOW": "低重要性"}.get(
                    item.importance.value,
                    "已记录",
                ),
                occurred_at=item.created_at,
                artifact_paths=self._paths_for_refs(item.related_artifacts, artifact_paths),
            )
            for item in state.findings
        ]
        hypotheses = [
            OutcomeRecord(
                title="待验证解释",
                detail=self._safe_text(item.statement),
                status_label=_STATUS_LABELS.get(item.status.value, "待验证"),
                certainty_label=self._confidence(item.confidence),
                occurred_at=item.created_at,
            )
            for item in state.hypotheses
        ]
        experiments = [
            OutcomeRecord(
                title=self._safe_text(item.goal),
                detail=self._experiment_detail(item.expected_result, item.actual_result),
                status_label=_STATUS_LABELS.get(item.status.value, "已记录"),
                certainty_label="受控实验",
                occurred_at=item.updated_at,
            )
            for item in state.experiments
        ]
        evidence = [
            OutcomeRecord(
                title="实验观察",
                detail=self._display_text(item.observation),
                status_label="已留存证据",
                certainty_label="不自动等同于结论",
                occurred_at=item.timestamp,
                artifact_paths=self._paths_for_refs(item.artifact_refs, artifact_paths),
            )
            for item in state.evidence
        ]
        return ChallengeOutcomes(
            flag=self._flag_outcome(manifest),
            facts=facts,
            findings=findings,
            hypotheses=hypotheses,
            experiments=experiments,
            evidence=evidence,
            artifacts=artifacts,
            web=self._web(manifest),
        )

    def _flag_outcome(
        self,
        manifest: Any,
    ) -> FlagOutcomeView:
        result = ChallengeFlagResultResolver().resolve(
            manifest.challenge_id,
            self.manager.paths_for(manifest).runs_dir,
        )
        if result.status == "FOUND":
            return FlagOutcomeView(
                status="found",
                status_label="已找到 Flag",
                value=result.value,
                source=result.source,
                evidence=result.evidence,
                evidence_paths=list(result.evidence_paths),
            )
        if result.status == "CONFLICT":
            return FlagOutcomeView(
                status="conflict",
                status_label="Flag 结果待核对",
                evidence_paths=list(result.evidence_paths),
                reason=result.reason,
            )
        return FlagOutcomeView(
            status="not_found",
            status_label="未找到 Flag",
            reason=result.reason,
        )

    def documents(self, challenge_id: str) -> ChallengeDocuments:
        manifest = self._manifest(challenge_id)
        paths = self.manager.paths_for(manifest)
        report = self._safe_markdown(paths.report_file)
        writeup = self._safe_markdown(paths.writeup_file)
        lessons = self._safe_markdown(paths.lessons_file)
        available = self._latest_run(manifest) is not None and "_Not generated._" not in report
        result = ChallengeFlagResultResolver().resolve(
            manifest.challenge_id,
            paths.runs_dir,
        )
        if result.status == "FOUND" and result.value:
            result_report = "\n".join(
                [
                    "# 最终结果",
                    "",
                    "## Flag",
                    "",
                    f"`{result.value}`",
                    "",
                    "## 支持证据",
                    "",
                    result.evidence or "已记录。",
                    "",
                    "## 证据文件路径",
                    "",
                    *(
                        f"- `{path}`" for path in result.evidence_paths
                    ),
                ]
            ).rstrip()
            report = f"{result_report}\n\n{report}".strip()
        return ChallengeDocuments(
            available=available,
            report=report if available else "",
            writeup=writeup if available else "",
            lessons=lessons if available else "",
        )

    def candidates(self, challenge_id: str) -> ExperienceCandidateCollection:
        manifest = self._manifest(challenge_id)
        path = self.manager.paths_for(manifest).experience_candidates_file
        store = ExperienceCandidateStore(path, challenge_id=challenge_id)
        return ExperienceCandidateCollection(
            items=[self._candidate(item) for item in store.list()]
        )

    def review_candidate(
        self,
        challenge_id: str,
        candidate_id: str,
        *,
        approved: bool,
    ) -> ExperienceCandidateView:
        manifest = self._manifest(challenge_id)
        path = self.manager.paths_for(manifest).experience_candidates_file
        candidate = ExperienceCandidateStore(path, challenge_id=challenge_id).get(candidate_id)
        if candidate is None or candidate.source_challenge != challenge_id:
            raise ValueError("未找到该经验候选项")
        catalog = ExperienceCandidateCatalog(
            self.settings.experience_root,
            self.settings.global_experience_path,
        )
        reviewed = catalog.approve(candidate_id) if approved else catalog.reject(candidate_id)
        return self._candidate(reviewed)

    def _artifacts(self, manifest: Any) -> list[ArtifactOutcome]:
        latest = self._latest_run(manifest)
        if latest is None:
            return []
        manifest_file = latest / "artifacts" / "manifest.json"
        raw = self._read_json(manifest_file, [])
        if not isinstance(raw, list):
            return []
        records: list[ArtifactOutcome] = []
        seen: set[str] = set()
        for item in raw:
            if not isinstance(item, Mapping):
                continue
            raw_path = item.get("path")
            if not isinstance(raw_path, str) or not raw_path:
                continue
            # Completed-run artifacts are already workspace-bound metadata;
            # keep the recorded filename so an operator can reconcile evidence.
            name = Path(raw_path).name or raw_path
            if not name or name in seen:
                continue
            seen.add(name)
            records.append(
                ArtifactOutcome(
                    artifact_id=(str(item["artifact_id"]) if item.get("artifact_id") else None),
                    name=name,
                    kind_label=self._artifact_label(str(item.get("artifact_type", ""))),
                    created_at=(
                        str(item["created_at"]) if item.get("created_at") else None
                    ),
                    path=raw_path,
                )
            )
        return records

    def _web(self, manifest: Any) -> WebOutcome:
        latest = self._latest_run(manifest)
        if latest is None:
            return WebOutcome()
        raw = self._read_json(latest / "checkpoint" / "domain_runtime.json", {})
        if not isinstance(raw, Mapping) or str(raw.get("domain", "")) != "web":
            return WebOutcome()
        try:
            state = WebRuntimeState.from_dict(raw)
        except (KeyError, TypeError, ValueError):
            return WebOutcome()
        endpoint_map: dict[str, WebEndpointOutcome] = {}
        for path in state.endpoints:
            normalized = self._safe_endpoint(path)
            if normalized:
                endpoint_map[normalized] = WebEndpointOutcome(path=normalized)
        for item in state.application_model.endpoints:
            path = self._safe_endpoint(item.path)
            if not path:
                continue
            parameters = [self._display_text(name) for name in item.parameters]
            endpoint_map[path] = WebEndpointOutcome(
                path=path,
                methods=sorted(set(item.methods)),
                parameters=sorted(set(parameters)),
                response_formats=sorted(set(self._display_text(v) for v in item.response_formats)),
                access_label=(
                    "需要认证"
                    if item.authentication_required is True
                    else "可匿名访问"
                    if item.authentication_required is False
                    else "访问状态未知"
                ),
            )
        technologies = sorted(
            set(
                [self._display_text(item) for item in state.technologies]
                + [self._display_text(item.name) for item in state.application_model.technologies]
            )
        )
        auth = state.application_model.authentication.status.value
        authentication_label = {
            "ANONYMOUS": "当前观察为匿名状态",
            "AUTHENTICATED": "已观察到认证状态",
            "CHALLENGED": "目标要求认证",
            "EXPIRED": "已观察到会话过期",
        }.get(auth, "认证状态未知")
        phase = {
            "RECON": "正在整理应用入口",
            "ANALYSIS": "正在分析证据关系",
            "EXPLOITATION": "正在验证重点假设",
            "VERIFY": "正在核对结果",
        }.get(state.phase.upper(), "Web 观察已建立")
        return WebOutcome(
            available=bool(endpoint_map or technologies),
            phase_label=phase or "Web 观察已建立",
            authentication_label=authentication_label,
            technologies=technologies,
            endpoints=sorted(endpoint_map.values(), key=lambda item: item.path),
        )

    def _safe_markdown(self, path: Path) -> str:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return ""
        lines: list[str] = []
        for line in text.splitlines():
            display = self._display_text(line)
            display = re.sub(r"`?(?:SOLVED|COMPLETED)`?", "已完成", display)
            display = re.sub(r"`?(?:FAILED|ABORTED|BLOCKED)`?", "本轮已结束", display)
            lines.append(display)
        rendered = "\n".join(lines).strip()
        replacements = {
            "# Challenge Report": "# 分析报告",
            "## Overview": "## 概览",
            "## Domain": "## 题目领域",
            "## Timeline": "## 阶段记录",
            "## Key Findings": "## 关键发现",
            "## Experiments": "## 实验结果",
            "## Evidence": "## 证据",
            "## Result": "## 本轮结果",
            "## Lessons Learned": "## 经验总结",
            "## Lessons": "## 可复用认识",
            "## Challenge Description": "## 题目描述",
            "## Recon": "## 初步观察",
            "## Analysis": "## 分析",
            "## Exploitation Process": "## 验证过程",
            "## Solution": "## 结论",
            "## Flag": "## 答案验证",
        }
        for source, target in replacements.items():
            rendered = rendered.replace(source, target)
        return rendered

    @staticmethod
    def _display_text(value: object) -> str:
        """Return challenge-local text verbatim for the authorized operator."""

        return str(value).strip()

    @staticmethod
    def _paths_for_refs(
        references: object,
        paths_by_id: Mapping[str, str | None],
    ) -> list[str]:
        result: list[str] = []
        if not isinstance(references, (list, tuple)):
            return result
        for reference in references:
            artifact_id = getattr(reference, "artifact_id", None)
            if artifact_id is None and isinstance(reference, Mapping):
                artifact_id = reference.get("artifact_id")
            path = paths_by_id.get(str(artifact_id))
            if path:
                result.append(path)
        return list(dict.fromkeys(result))

    def _safe_text(self, value: object) -> str:
        return self._display_text(value)

    def _experiment_detail(self, expected: str, actual: str) -> str:
        expected_text = self._safe_text(expected)
        actual_text = self._safe_text(actual)
        if actual_text:
            return f"预期：{expected_text}\n\n观察：{actual_text}"
        return f"预期：{expected_text}\n\n尚未记录实际观察。"

    @staticmethod
    def _confidence(value: object) -> str:
        raw = str(getattr(value, "value", value)).upper()
        if raw in _CONFIDENCE_LABELS:
            return _CONFIDENCE_LABELS[raw]
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return "置信度待评估"
        return "高置信度" if numeric >= 0.75 else "中等置信度" if numeric >= 0.45 else "低置信度"

    @staticmethod
    def _artifact_label(value: str) -> str:
        labels = {
            "http_response": "响应记录",
            "web_intelligence": "网页观察",
            "analysis": "分析材料",
            "text": "文本材料",
        }
        return labels.get(value.lower(), "分析材料")

    def _safe_endpoint(self, value: str) -> str:
        return repeatedly_unquote(str(value).strip())

    def _candidate(self, item: ExperienceCandidate) -> ExperienceCandidateView:
        return ExperienceCandidateView(
            candidate_id=item.id,
            category_label=_CATEGORY_LABELS.get(item.category, "通用经验"),
            kind_label=_KIND_LABELS.get(item.lesson_kind, "通用认识"),
            pattern=self._safe_text(item.pattern),
            strategy=self._safe_text(item.strategy),
            lesson=self._safe_text(item.lesson),
            confidence_label=self._confidence(item.confidence),
            status=item.review_status.value,
            status_label=_REVIEW_LABELS[item.review_status.value],
        )

    def _manifest(self, challenge_id: str):
        manifest = self.manager.store.get(challenge_id)
        if manifest is None:
            raise ValueError("未找到该题目")
        return manifest

    @staticmethod
    def _intelligence(path: Path, challenge_id: str) -> IntelligenceState:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("题目成果暂时无法读取") from error
        if not isinstance(raw, Mapping):
            raise ValueError("题目成果格式无效")
        state = IntelligenceState.from_dict(raw)
        if state.challenge_id != challenge_id:
            raise ValueError("题目成果不属于当前题目")
        return state

    def _latest_run(self, manifest: Any) -> Path | None:
        runs = self.manager.paths_for(manifest).runs_dir
        candidates = [
            item
            for item in runs.glob("run-*")
            if item.is_dir() and (item / "run.json").is_file()
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda item: int(item.name.rsplit("-", 1)[-1]))

    @staticmethod
    def _read_json(path: Path, fallback: Any) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return fallback
