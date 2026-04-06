from enum import Enum


class State(str, Enum):
    INIT = "INIT"
    INTERVIEW = "INTERVIEW"
    IR_READY = "IR_READY"
    PLANNED = "PLANNED"
    COMPOSED = "COMPOSED"
    VALIDATED = "VALIDATED"
    DOT_GENERATED = "DOT_GENERATED"
    COMPLETE = "COMPLETE"


# Deterministic transition table
VALID_TRANSITIONS: dict[State, list[State]] = {
    State.INIT:          [State.INTERVIEW],
    State.INTERVIEW:     [State.IR_READY],
    State.IR_READY:      [State.PLANNED],
    State.PLANNED:       [State.COMPOSED],
    State.COMPOSED:      [State.VALIDATED],
    State.VALIDATED:     [State.DOT_GENERATED],
    State.DOT_GENERATED: [State.COMPLETE],
    State.COMPLETE:      [],
}


def transition(current: State, target: State) -> State:
    if target not in VALID_TRANSITIONS.get(current, []):
        raise ValueError(
            f"Invalid transition: {current} → {target}. "
            f"Valid from {current}: {VALID_TRANSITIONS[current]}"
        )
    return target
