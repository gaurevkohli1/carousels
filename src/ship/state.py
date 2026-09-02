"""One drop, one state file.

The source playbook logs publish attempts. A log tells you what broke; it does
not stop a retry from posting twice. This does: each drop moves through a fixed
sequence of states, every transition is written to disk immediately, and a run
that resumes skips whatever is already done.

    draft -> rendered -> uploaded -> ig_published -> fb_published -> measured

A crashed run resumes from its last state. A re-run of a completed stage is a
no-op rather than a duplicate post.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib

ORDER = ["draft", "rendered", "uploaded", "ig_published", "fb_published", "measured"]


class StateError(RuntimeError):
    pass


class Drop:
    def __init__(self, drop_dir: pathlib.Path):
        self.dir = pathlib.Path(drop_dir).resolve()
        self.path = self.dir / "state.json"
        self.data = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            return json.loads(self.path.read_text())
        return {
            "drop": self.dir.name,
            "state": "draft",
            "history": [],
            "receipts": {},
        }

    def _save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2) + "\n")

    @property
    def state(self) -> str:
        return self.data["state"]

    def reached(self, state: str) -> bool:
        """Has the drop already got at least this far?"""
        if state not in ORDER:
            raise StateError(f"unknown state {state!r}")
        return ORDER.index(self.data["state"]) >= ORDER.index(state)

    def advance(self, state: str, receipt: dict | None = None) -> None:
        if state not in ORDER:
            raise StateError(f"unknown state {state!r}")
        if ORDER.index(state) < ORDER.index(self.data["state"]):
            raise StateError(
                f"cannot move backwards from {self.data['state']!r} to {state!r}"
            )
        self.data["state"] = state
        self.data["history"].append({
            "state": state,
            "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        })
        if receipt:
            self.data["receipts"][state] = receipt
        self._save()

    def receipt(self, state: str) -> dict:
        return self.data["receipts"].get(state, {})
