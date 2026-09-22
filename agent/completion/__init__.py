"""R8.6 challenge completion and reviewed experience consolidation."""

from agent.completion.collector import (
    ChallengeCompletionPipeline,
    CompletionCollector,
    CompletionOutputs,
    CompletionSnapshot,
)
from agent.completion.experience import (
    ExperienceCandidateCatalog,
    ExperienceCandidateExtractor,
    ExperienceCandidateStore,
)
from agent.completion.models import (
    ChallengeReport,
    ExperienceCandidate,
    ExperienceReviewStatus,
)
from agent.completion.report import ReportGenerator
from agent.completion.writeup import WriteupGenerator

__all__ = [
    "ChallengeReport",
    "ChallengeCompletionPipeline",
    "CompletionCollector",
    "CompletionOutputs",
    "CompletionSnapshot",
    "ExperienceCandidate",
    "ExperienceCandidateCatalog",
    "ExperienceCandidateExtractor",
    "ExperienceCandidateStore",
    "ExperienceReviewStatus",
    "ReportGenerator",
    "WriteupGenerator",
]
