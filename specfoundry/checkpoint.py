"""Checkpoint manager — save and resume pipeline state after each phase."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .state_machine import State
from .ir import SpecIR


@dataclass
class Checkpoint:
    state: State
    ir: SpecIR
    idea: str = ""                                           # original user idea
    spec_plan: list[dict] = field(default_factory=list)
    outputs: dict[str, str] = field(default_factory=dict)   # filename → content


class CheckpointManager:
    def __init__(self, output_dir: Path):
        self._dir = output_dir / ".specfoundry"
        self._file = self._dir / "checkpoint.json"

    def exists(self) -> bool:
        return self._file.exists()

    def save(self, cp: Checkpoint) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        data = {
            "state": cp.state.value,
            "ir": cp.ir.to_dict(),
            "idea": cp.idea,
            "spec_plan": cp.spec_plan,
            "outputs": cp.outputs,
        }
        # Atomic write via tmp → rename
        tmp = self._file.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(self._file)

    def load(self) -> Checkpoint:
        data = json.loads(self._file.read_text(encoding="utf-8"))
        return Checkpoint(
            state=State(data["state"]),
            ir=SpecIR.from_dict(data["ir"]),
            idea=data.get("idea", ""),
            spec_plan=data.get("spec_plan", []),
            outputs=data.get("outputs", {}),
        )
