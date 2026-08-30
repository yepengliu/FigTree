"""
Data structures for inter-node communication in FIGTREE.

Every field is JSON-serializable so it can be saved to disk as intermediate logs.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Global style spec, created by the root and read-only for descendants
# ---------------------------------------------------------------------------

DEFAULT_GLOBAL_STYLE: Dict[str, Any] = {
    "font_family": "Times New Roman, serif",
    "font_sizes": {
        "title": 16,
        "block_label": 12,
        "annotation": 10,
        "math": 13,
    },
    "stroke_widths": {
        "main_arrow": 1.2,
        "skip_arrow": 1.6,
        "container_border": 1.5,
        "card_border": 1.2,
    },
    "corner_radius": {
        "container": 8,
        "card": 6,
        "small": 4,
    },
    "grid": 4,
    "min_gap": 12,
    "min_arrow_distance": 20,
    "padding": 24,
    "arrow_rules": {
        "min_arrow_distance": 20,
        "marker_width": 5,
        "marker_height": 3.5,
        "terminal_segment_min": 20,
        "allow_diagonal": False,
    },
    "palette": {
        "encoder": ["#D6EAFF", "#B8D4F0"],
        "processor": ["#FFE4B5", "#FFA500"],
        "decoder": ["#D4F0E0", "#A8DFC0"],
        "container_bg": "#F5F7FA",
        "container_border": "#E8ECF0",
        "arrow_main": "#333333",
        "arrow_skip": "#999999",
        "text_primary": "#2C3E50",
        "text_secondary": "#666666",
    },
}


# ---------------------------------------------------------------------------
# TaskPackage: parent to child
# ---------------------------------------------------------------------------

@dataclass
class TaskPackage:
    task_id: str
    description: str
    paper_excerpt: str
    canvas: Dict[str, int]              # {"w": 400, "h": 300}
    global_style: Dict[str, Any]
    required_ports: Dict[str, Any] = field(default_factory=dict)
    fix_instructions: List[Dict] = field(default_factory=list)
    depth: int = 0
    max_depth: int = 3
    parent_id: Optional[str] = None
    reference_image_path: Optional[str] = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)

    def save(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json())

    @classmethod
    def from_json(cls, text: str) -> "TaskPackage":
        return cls(**json.loads(text))


# ---------------------------------------------------------------------------
# NodeReport: child to parent
# ---------------------------------------------------------------------------

@dataclass
class NodeReport:
    task_id: str
    status: str                         # "ok" | "failed" | "retry_needed"
    svg: str = ""
    bbox: Dict[str, int] = field(default_factory=lambda: {"w": 0, "h": 0})
    ports: Dict[str, Dict[str, int]] = field(default_factory=dict)
    issues_remaining: List[Dict] = field(default_factory=list)
    message: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)

    def save(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json())


# ---------------------------------------------------------------------------
# IssueReport: critic output
# ---------------------------------------------------------------------------

@dataclass
class IssueReport:
    issue_id: str
    severity: str                       # "critical" | "warning"
    visual_description: str
    code_anchor: Dict[str, Any] = field(default_factory=dict)
    fix_instruction: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# DecompositionPlan: generator output when decomposing
# ---------------------------------------------------------------------------

@dataclass
class DecompositionPlan:
    should_decompose: bool
    child_tasks: List[Dict[str, Any]] = field(default_factory=list)
    svg: str = ""  # only set if should_decompose is False (leaf node)
    reasoning: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# LLM Call Log Entry
# ---------------------------------------------------------------------------

@dataclass
class LLMCallLog:
    timestamp: str
    node_id: str
    character: str          # "generator" | "critic" | "svg_worker"
    prompt_summary: str     # first 500 chars of prompt
    prompt_full_path: str   # path to full prompt file
    response_summary: str   # first 500 chars of response
    response_full_path: str # path to full response file
    duration_seconds: float
    success: bool
    error: str = ""

    def to_json_line(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

