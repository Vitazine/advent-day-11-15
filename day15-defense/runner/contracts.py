"""Immutable source and decision contracts. No execution authority in input data."""
from dataclasses import dataclass

@dataclass(frozen=True)
class ReviewFile:
    path: str
    content: str

@dataclass(frozen=True)
class Snapshot:
    id: str
    artifact_hash: str
    files: tuple[ReviewFile, ...]

@dataclass(frozen=True)
class RunResult:
    status: str
    exit_code: int | None
    evidence_id: str
    artifact_hash: str
    reason_codes: tuple[str, ...] = ()

@dataclass(frozen=True)
class CheckResult:
    status: str
    artifact_hash: str
    policy_hash: str
    reason_codes: tuple[str, ...]
    evidence_id: str

@dataclass(frozen=True)
class GateDecision:
    status: str
    snapshot_id: str
    artifact_hash: str
    policy_hash: str
    reason_codes: tuple[str, ...]

@dataclass(frozen=True)
class AcceptedArtifact:
    artifact_hash: str
    commit_id: str | None = None

@dataclass(frozen=True)
class JobRequest:
    source: object
    task: str = ''
    profile: str = 'python-fastapi'
