"""Independent asyncio handlers with a deterministic, injected timer queue.

The four-version patch split is synthetic. Its failing API sequence reconstructs
CPython bpo-21886 (https://github.com/python/cpython/issues/66085), not the original
CPython branches or event loop. No model transition code is used here.
"""

import asyncio
from collections import deque
from dataclasses import dataclass

from .fixtures.cancellation.base.scheduler import Scheduler as BaseScheduler
from .fixtures.cancellation.base.completion import Completer as BaseCompleter
from .fixtures.cancellation.left.scheduler import Scheduler as LeftScheduler
from .fixtures.cancellation.left.completion import Completer as LeftCompleter
from .fixtures.cancellation.right.scheduler import Scheduler as RightScheduler
from .fixtures.cancellation.right.completion import Completer as RightCompleter
from .fixtures.cancellation.merged.scheduler import Scheduler as MergedScheduler
from .fixtures.cancellation.merged.completion import Completer as MergedCompleter

EVIDENCE = {
    "kind": "historical_failure_reconstruction_with_synthetic_branch_split",
    "issue": "https://github.com/python/cpython/issues/66085",
    "original_issue": "https://bugs.python.org/issue21886",
    "invariant": "no_completion_after_cancellation",
    "scope": "Actual asyncio.Future with an injected timer queue; not historical CPython revisions or a full event loop.",
}


@dataclass(frozen=True)
class CallbackRevision:
    scheduler: type
    completer: type
    scheduler_path: str
    completer_path: str

    @property
    def sources(self):
        return {"scheduler": self.scheduler_path, "completer": self.completer_path}


def _revision(name, scheduler, completer, completion_name=None):
    return CallbackRevision(scheduler, completer, f"fixtures/cancellation/{name}/scheduler.py",
                            f"fixtures/cancellation/{completion_name or name}/completion.py")


CONFLICT_REVISIONS = {
    "base": _revision("base", BaseScheduler, BaseCompleter),
    "left": _revision("left", LeftScheduler, LeftCompleter),
    "right": _revision("right", RightScheduler, RightCompleter),
    "merged": _revision("merged", MergedScheduler, MergedCompleter),
}
FIXED_REVISIONS = {
    **CONFLICT_REVISIONS,
    "right": _revision("right", RightScheduler, BaseCompleter, "base"),
    "merged": _revision("merged", MergedScheduler, LeftCompleter, "left"),
}
CONFLICT_CONFIGS = {
    "base": {"deferred": False, "guard_cancelled": True},
    "left": {"deferred": True, "guard_cancelled": True},
    "right": {"deferred": False, "guard_cancelled": False},
    "merged": {"deferred": True, "guard_cancelled": False},
}
FIXED_CONFIGS = {version: {**config, "guard_cancelled": True}
                 for version, config in CONFLICT_CONFIGS.items()}


class ManualLoop:
    """Only the Future/debug and timer APIs exercised by this bounded fixture."""

    def __init__(self):
        self.pending = deque()
        self.errors = []
        self.now = 0

    def get_debug(self):
        return False

    def call_later(self, delay, callback, *args):
        self.pending.append((self.now + delay, callback, args))

    def fire_next(self):
        deadline, callback, args = self.pending.popleft()
        self.now = deadline
        try:
            callback(*args)
        except asyncio.InvalidStateError as error:
            # The real loop reports a callback error and continues. Capture that
            # observable error; do not replace it with a model-derived result.
            self.errors.append({"type": type(error).__name__})


class CancellationRuntime:
    def __init__(self, revision):
        self.loop = ManualLoop()
        self.scheduler = revision.scheduler()
        self.completer = revision.completer()
        self.future = None

    def enabled(self):
        events = []
        if self.future is None:
            events.append("start")
        elif not self.future.done():
            events.append("cancel")
        if self.loop.pending:
            events.append("fire_callback")
        return tuple(sorted(events))

    def dispatch(self, event):
        if event not in self.enabled():
            return False
        if event == "start":
            self.future = asyncio.Future(loop=self.loop)
            self.scheduler.start(self.loop, self.future, self.completer)
        elif event == "cancel":
            self.future.cancel()
        elif event == "fire_callback":
            self.loop.fire_next()
        return True

    def snapshot(self):
        future_state = "absent"
        value = None
        if self.future is not None:
            future_state = ("cancelled" if self.future.cancelled() else
                            "finished" if self.future.done() else "pending")
            if future_state == "finished":
                value = self.future.result()
        violations = ["no_completion_after_cancellation"] if self.loop.errors else []
        return {"state": {"future": future_state, "callbacks": len(self.loop.pending),
                          "errors": len(self.loop.errors)},
                "enabled": list(self.enabled()), "effect_records": list(self.completer.records),
                "error_records": list(self.loop.errors), "result": value,
                "violations": violations, "passed": not violations, "clock": self.loop.now}

    @staticmethod
    def expected_observations(state, config=None):
        finished = state["future"] == "finished"
        return {"effect_records": [{"result": "ready"}] if finished else [],
                "error_records": [{"type": "InvalidStateError"}] * state["errors"],
                "result": "ready" if finished else None}
