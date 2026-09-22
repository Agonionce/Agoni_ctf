"""Local-only R12 Web benchmark contracts and deterministic runner."""

from agent.domains.web.benchmark.loader import WebBenchmarkLoader
from agent.domains.web.benchmark.models import (
    WebBenchmarkCase,
    WebBenchmarkEvaluationRecord,
    WebBenchmarkResult,
    WebBenchmarkRunSnapshot,
)
from agent.domains.web.benchmark.report import (
    WebBenchmarkPerformanceReport,
    WebBenchmarkReportBuilder,
)
from agent.domains.web.benchmark.runner import WebBenchmarkRunner

__all__ = [
    "WebBenchmarkCase",
    "WebBenchmarkLoader",
    "WebBenchmarkEvaluationRecord",
    "WebBenchmarkPerformanceReport",
    "WebBenchmarkReportBuilder",
    "WebBenchmarkResult",
    "WebBenchmarkRunSnapshot",
    "WebBenchmarkRunner",
]
