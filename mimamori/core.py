"""Pure incident logic. A check is an observation, not proof of continuous uptime."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Observation:
    target_id: str
    slot: int
    ok: bool
    latency_ms: int
    reason: str
    status: int | None = None
    tls_days: int | None = None
    observed_at: int | None = None


def initial_state():
    return {"last_slot": -1, "status": "UNKNOWN", "failures": 0,
            "successes": 0, "pending": None}


def advance(previous, observation):
    """Two failed samples open an incident; two good samples resolve it."""
    if observation.slot <= previous["last_slot"]:
        return None
    if previous["pending"]:
        raise RuntimeError("deliver the pending notification before advancing state")
    state = dict(previous)
    state["last_slot"] = observation.slot
    state["failures"] = 0 if observation.ok else previous["failures"] + 1
    state["successes"] = previous["successes"] + 1 if observation.ok else 0
    # Missing intervals break a consecutive streak.
    if previous["last_slot"] >= 0 and observation.slot - previous["last_slot"] > 300:
        state["failures"] = int(not observation.ok)
        state["successes"] = int(observation.ok)
    if observation.ok and state["status"] == "UNKNOWN":
        state["status"] = "UP"
    if state["failures"] >= 2:
        state["status"] = "DOWN"
    elif state["successes"] >= 2:
        state["status"] = "UP"
    if state["status"] != previous["status"] and (
        state["status"] == "DOWN" or previous["status"] == "DOWN"
    ):
        state["pending"] = {
            "id": f"{observation.target_id}:{observation.slot}:{state['status']}",
            "target_id": observation.target_id,
            "status": state["status"], "slot": observation.slot,
            "reason": observation.reason,
        }
    return state


def flush_pending(store, target_id, notify):
    state = store.state(target_id)
    if state["pending"]:
        # Publish first: a crash before acknowledgement may redeliver the same ID.
        # This is at-least-once delivery, never an exactly-once claim.
        notify(state["pending"])
        store.ack(target_id, state)


def process(store, observation, notify):
    flush_pending(store, observation.target_id, notify)
    previous = store.state(observation.target_id)
    updated = advance(previous, observation)
    if updated is None:
        return False
    committed = store.commit(previous, updated, asdict(observation))
    if committed:
        flush_pending(store, observation.target_id, notify)
    return committed
