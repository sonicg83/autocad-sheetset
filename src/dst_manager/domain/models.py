from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class JobStatus(StrEnum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    QUEUED = "QUEUED"
    STAGING = "STAGING"
    CAD_RUNNING = "CAD_RUNNING"
    VERIFYING = "VERIFYING"
    PREPARED = "PREPARED"
    PUBLISHING = "PUBLISHING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    BLOCKED_FILE_LOCK = "BLOCKED_FILE_LOCK"
    ROLLING_BACK = "ROLLING_BACK"
    ROLLED_BACK = "ROLLED_BACK"
    NEEDS_REVIEW = "NEEDS_REVIEW"


@dataclass(slots=True)
class ValidationIssue:
    code: str
    severity: Severity
    message: str
    object_id: str | None = None
    location: str | None = None


@dataclass(slots=True)
class LayoutReference:
    file_name: str
    relative_file_name: str
    layout_name: str
    handle: str
    resolved_path: Path | None = None
    resolution_source: str | None = None


@dataclass(slots=True)
class Sheet:
    acsm_id: str
    number: str
    title: str
    layout: LayoutReference
    custom_properties: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class Subset:
    acsm_id: str
    name: str
    order: int
    sheets: list[Sheet] = field(default_factory=list)


@dataclass(slots=True)
class SheetSetDocument:
    database_id: str
    name: str
    subsets: list[Subset]
    custom_properties: dict[str, str] = field(default_factory=dict)
    diagnostics: list[ValidationIssue] = field(default_factory=list)

    @property
    def sheets(self) -> list[Sheet]:
        return [sheet for subset in self.subsets for sheet in subset.sheets]


@dataclass(slots=True)
class Workspace:
    id: str
    root: Path
    dst_path: Path
    revision_id: str
    document: SheetSetDocument
    unreferenced_dwgs: list[Path] = field(default_factory=list)
