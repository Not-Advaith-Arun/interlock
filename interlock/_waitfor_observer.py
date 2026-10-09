"""Private sandbox entrypoint for one audited historical source observation."""

import resource

import asyncio
import enum
import functools
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
from types import SimpleNamespace, TracebackType
from typing import final, Optional, Type
import unittest


def file_digest(path):
    fingerprint = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024**2), b""):
            fingerprint.update(block)
    return fingerprint.hexdigest()


def load_sources(policy, expected_manifest):
    root = Path("/case/fixture")
    manifest_bytes = (root / "manifest.json").read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != expected_manifest:
        raise ValueError("sandbox manifest identity changed")
    manifest = json.loads(manifest_bytes)
    files = {}
    for name, metadata in manifest["files"].items():
        raw = (root / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != metadata["sha256"] or len(raw) != metadata["bytes"]:
            raise ValueError("sandbox selected source identity changed")
        files[name] = raw
    timeouts = {"__name__": "pinned_timeouts", "enum": enum, "TracebackType": TracebackType,
                "final": final, "Optional": Optional, "Type": Type, "events": asyncio.events,
                "exceptions": asyncio.exceptions, "tasks": asyncio.tasks}
    exec(compile(files["timeouts.py"], "pinned/timeouts.py", "exec"), timeouts)
    namespace = {"__name__": "pinned_" + policy, "events": asyncio.events,
                 "exceptions": asyncio.exceptions, "ensure_future": asyncio.ensure_future,
                 "functools": functools, "timeouts": SimpleNamespace(**timeouts)}
    exec(compile(files[policy + ".py"], "pinned/" + policy + ".py", "exec"), namespace)
    return namespace, timeouts, files


class ObservedLoop(asyncio.SelectorEventLoop):
    def __init__(self, source, timeout_class):
        super().__init__()
        self.deadlines = []
        self.fired = []
        self.errors = []
        self.events = []
        self.release_waiter = source["_release_waiter"]
        self.timeout_class = timeout_class
        self.set_exception_handler(lambda loop, context: self.errors.append(str(context.get("exception", context.get("message")))))

    def call_at(self, when, callback, *args, context=None):
        deadline = (callback is self.release_waiter or
                    (isinstance(getattr(callback, "__self__", None), self.timeout_class)
                     and callback.__name__ == "_on_timeout"))
        if deadline:
            identity = len(self.deadlines)
            self.deadlines.append({"id": identity, "callback": callback.__name__, "delay": when - self.time()})
            original = callback
            def fire(*arguments):
                self.fired.append(identity)
                self.events.append("deadline_fired")
                return original(*arguments)
            callback = fire
        return super().call_at(when, callback, *args, context=context)


async def observe(wait_for, case):
    events = asyncio.get_running_loop().events
    suppressed = False
    completed = case in ("completed_external", "no_cancel")
    external = case.endswith("external")
    timer = case.startswith("timeout")
    reached_end = False

    async def inner():
        nonlocal suppressed
        events.append("inner_start")
        if completed:
            events.append("inner_result")
            return "done"
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            events.append("inner_cancelled")
            if case == "timeout_suppressed":
                suppressed = True
                events.append("inner_suppressed")
                return 42
            raise

    inner_task = asyncio.create_task(inner())

    async def outer():
        nonlocal reached_end
        events.append("outer_start")
        value = await wait_for(inner_task, timeout=0.01 if timer else 100)
        events.append("wait_returned")
        await asyncio.sleep(1)
        reached_end = True
        events.append("reached_end")
        return value

    outer_task = asyncio.create_task(outer())
    await asyncio.sleep(0)
    preconditions = {"inner_done_before_cancel": inner_task.done(),
                     "outer_pending_before_cancel": not outer_task.done(),
                     "inner_value_before_cancel": inner_task.result() if inner_task.done() else None}
    accepted = False
    if external:
        events.append("external_cancel")
        accepted = outer_task.cancel()
    value = None
    try:
        value = await outer_task
        termination = "returned"
    except asyncio.CancelledError:
        termination = "cancelled"
    except TimeoutError:
        termination = "timed_out"
    inner_state = ("cancelled" if inner_task.cancelled() else
                   "suppressed_result" if suppressed else "result" if inner_task.done() else "pending")
    return {"outer": termination, "inner": inner_state, "result": value,
            "cancel_accepted": accepted, "reached_end": reached_end,
            "origin": "external" if external else "timer" if timer else "none",
            "suppressed": suppressed,
            "violation": accepted and (termination == "returned" or reached_end),
            "inner_result": inner_task.result() if inner_task.done() and not inner_task.cancelled() else None,
            "external_requests": int(external), "preconditions": preconditions, "events": events}


async def upstream(wait_for, raw):
    facade = SimpleNamespace(create_task=asyncio.create_task, sleep=asyncio.sleep,
                             CancelledError=asyncio.CancelledError, wait_for=wait_for)
    namespace = {"asyncio": facade}
    exec(compile(raw, "pinned/regression.py", "exec"), namespace)
    try:
        await namespace["test_wait_for_issue86296"](unittest.TestCase())
    except AssertionError as exc:
        return {"outcome": "assertion_failed", "message": str(exc)}
    return {"outcome": "passed", "message": None}


def main():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024**2, 512 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CPU, (5, 6))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024**2, 1024**2))
    policy, case, manifest_sha = sys.argv[1:]
    if policy not in ("before", "fix") or case not in (
            "upstream", "completed_external", "pending_external", "no_cancel", "timeout", "timeout_suppressed"):
        raise ValueError("unknown historical observation")
    if sys.version_info < (3, 11):
        raise ValueError("historical observation requires Python 3.11+")
    source, timeouts, files = load_sources(policy, manifest_sha)
    loop = ObservedLoop(source, timeouts["Timeout"])
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(upstream(source["wait_for"], files["regression.py"]) if case == "upstream"
                                         else observe(source["wait_for"], case))
        observation = {"format": "interlock-waitfor-observation/v1", "policy": policy, "case": case,
                       "manifest_sha256": manifest_sha, "result": result,
                       "deadlines": loop.deadlines, "deadlines_fired": loop.fired,
                       "callback_errors": loop.errors,
                       "pending_tasks": len(asyncio.all_tasks(loop)),
                       "runtime": {"python": platform.python_version(), "implementation": platform.python_implementation(),
                                   "executable": sys.executable,
                                   "executable_sha256": file_digest("/proc/self/exe"),
                                   "rlimits": {name: list(resource.getrlimit(kind)) for name, kind in (
                                       ("core", resource.RLIMIT_CORE), ("address_space", resource.RLIMIT_AS),
                                       ("cpu", resource.RLIMIT_CPU), ("file_size", resource.RLIMIT_FSIZE))},
                                   "asyncio_sources": {name: hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
                                                       for name, module in (("tasks", asyncio.tasks), ("events", asyncio.events),
                                                                            ("futures", asyncio.futures), ("exceptions", asyncio.exceptions))}},
                       "isolation": {"network_namespace": os.readlink("/proc/self/ns/net"),
                                     "home_visible": Path("/home").exists(), "environment": dict(os.environ)}}
    finally:
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()
    print(json.dumps(observation), flush=True)


if __name__ == "__main__":
    main()
