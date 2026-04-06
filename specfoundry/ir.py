"""Spec IR — canonical intermediate representation of gathered requirements."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
import json

import yaml


@dataclass
class ProductInfo:
    name: str = ""
    summary: str = ""
    app_type: str = ""       # web | cli | api | mobile | ai-agent | library | other
    description: str = ""


@dataclass
class UserRole:
    role: str = ""
    goals: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)


@dataclass
class Workflow:
    name: str = ""
    actor: str = ""
    trigger: str = ""
    steps: list[str] = field(default_factory=list)
    success_result: str = ""
    failure_modes: list[str] = field(default_factory=list)
    acceptance_tests: list[str] = field(default_factory=list)


@dataclass
class EntityField:
    name: str = ""
    type: str = ""
    required: bool = True
    description: str = ""


@dataclass
class Entity:
    name: str = ""
    fields: list[EntityField] = field(default_factory=list)
    invariants: list[str] = field(default_factory=list)
    lifecycle: str = ""
    relationships: list[str] = field(default_factory=list)


@dataclass
class API:
    method: str = ""
    path: str = ""
    auth: str = ""
    request_schema: dict = field(default_factory=dict)
    response_schema: dict = field(default_factory=dict)
    error_conditions: list[str] = field(default_factory=list)
    rate_limits: str = ""
    idempotent: bool = False


@dataclass
class BackgroundJob:
    name: str = ""
    trigger: str = ""
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    retries: int = 3
    timeout_seconds: int = 300
    observability: str = ""
    human_override: str = ""


@dataclass
class DeploymentInfo:
    target: str = ""
    cloud: str = ""
    backend_framework: str = ""
    frontend_framework: str = ""
    database: str = ""
    cache: str = ""
    message_queue: str = ""


@dataclass
class SecurityInfo:
    auth_method: str = ""
    authorization_model: str = ""
    data_sensitivity: str = ""
    compliance: list[str] = field(default_factory=list)


@dataclass
class SpecIR:
    product: ProductInfo = field(default_factory=ProductInfo)
    users: list[UserRole] = field(default_factory=list)
    workflows: list[Workflow] = field(default_factory=list)
    entities: list[Entity] = field(default_factory=list)
    apis: list[API] = field(default_factory=list)
    background_jobs: list[BackgroundJob] = field(default_factory=list)
    deployment: DeploymentInfo = field(default_factory=DeploymentInfo)
    security: SecurityInfo = field(default_factory=SecurityInfo)
    quality_attributes: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    interview_transcript: list[dict] = field(default_factory=list)
    is_ai_heavy: bool = False
    completeness: float = 0.0

    # ── Serialisation ──────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def to_yaml(self) -> str:
        return yaml.dump(self.to_dict(), default_flow_style=False,
                         allow_unicode=True, sort_keys=False)

    @classmethod
    def from_dict(cls, data: dict) -> SpecIR:
        ir = cls()
        _safe = lambda d, keys: {k: v for k, v in d.items() if k in keys}

        if p := data.get("product"):
            ir.product = ProductInfo(**_safe(p, ProductInfo.__dataclass_fields__))

        ir.users = [
            UserRole(**_safe(u, UserRole.__dataclass_fields__))
            for u in data.get("users", [])
        ]
        ir.workflows = [
            Workflow(**_safe(w, Workflow.__dataclass_fields__))
            for w in data.get("workflows", [])
        ]

        for e in data.get("entities", []):
            raw_fields = e.get("fields", [])
            ef = [
                EntityField(**_safe(f, EntityField.__dataclass_fields__))
                for f in raw_fields
            ]
            ir.entities.append(Entity(
                name=e.get("name", ""),
                fields=ef,
                invariants=e.get("invariants", []),
                lifecycle=e.get("lifecycle", ""),
                relationships=e.get("relationships", []),
            ))

        ir.apis = [
            API(**_safe(a, API.__dataclass_fields__))
            for a in data.get("apis", [])
        ]
        ir.background_jobs = [
            BackgroundJob(**_safe(b, BackgroundJob.__dataclass_fields__))
            for b in data.get("background_jobs", [])
        ]

        if d := data.get("deployment"):
            ir.deployment = DeploymentInfo(**_safe(d, DeploymentInfo.__dataclass_fields__))
        if s := data.get("security"):
            ir.security = SecurityInfo(**_safe(s, SecurityInfo.__dataclass_fields__))

        ir.quality_attributes = data.get("quality_attributes", [])
        ir.acceptance_criteria = data.get("acceptance_criteria", [])
        ir.open_questions = data.get("open_questions", [])
        ir.interview_transcript = data.get("interview_transcript", [])
        ir.is_ai_heavy = bool(data.get("is_ai_heavy", False))
        ir.completeness = float(data.get("completeness", 0.0))
        return ir

    @classmethod
    def from_json(cls, s: str) -> SpecIR:
        return cls.from_dict(json.loads(s))

    # ── Completeness ───────────────────────────────────────────────────────────

    def compute_completeness(self) -> float:
        checks = [
            bool(self.product.name),
            bool(self.product.summary),
            len(self.users) > 0,
            len(self.workflows) > 0,
            len(self.entities) > 0,
            bool(self.deployment.target),
            bool(self.security.auth_method),
            len(self.quality_attributes) > 0,
            len(self.acceptance_criteria) > 0,
            len(self.apis) > 0 or self.product.app_type in ("cli", "library"),
        ]
        self.completeness = sum(checks) / len(checks)
        return self.completeness

    def missing_domains(self) -> list[str]:
        missing: list[str] = []
        if not self.product.name or not self.product.summary:
            missing.append("product overview")
        if not self.users:
            missing.append("user roles")
        if not self.workflows:
            missing.append("user workflows")
        if not self.entities:
            missing.append("data model / entities")
        if not self.apis and self.product.app_type not in ("cli", "library"):
            missing.append("API contracts")
        if not self.deployment.target:
            missing.append("deployment / infrastructure")
        if not self.security.auth_method:
            missing.append("security / authentication")
        if not self.quality_attributes:
            missing.append("quality attributes")
        if not self.acceptance_criteria:
            missing.append("acceptance criteria")
        return missing
