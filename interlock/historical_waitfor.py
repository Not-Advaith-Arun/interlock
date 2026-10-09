"""Opt-in, source-pinned historical pair calibration, separate from merge checks."""

import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import selectors
import shutil
import signal
import subprocess
import sys
import tempfile
import time

from .waitfor_model import CASES, POLICIES, model_report

MANIFEST_SHA256 = "572ee706bbd4e4c9f91cbed0352c8d3a4576fb7421911c3ea31c2f4058cba287"
FIXTURE = Path(__file__).parent / "fixtures" / "historical_waitfor"
FILES = {"before.py", "fix.py", "timeouts.py", "regression.py", "LICENSE"}
RLIMITS = {"core": [0, 0], "address_space": [512 * 1024**2] * 2,
           "cpu": [5, 6], "file_size": [1024**2] * 2}
EXIT_CODES = {"calibrated": 0, "model_only": 0, "source_drift": 2, "incomplete": 3,
              "unsupported": 3, "model_mismatch": 4, "expectation_failed": 1}


def expected_projection(policy, case):
    """Independent contract oracle, not derived from model transitions or handlers."""
    external = case in ("completed_external", "pending_external")
    suppressed = case == "timeout_suppressed"
    faulty = case == "completed_external" and policy == "before"
    returned = faulty or case in ("no_cancel", "timeout_suppressed")
    return {"outer": "returned" if returned else "cancelled" if external else "timed_out",
            "inner": "result" if case in ("completed_external", "no_cancel") else
                     "suppressed_result" if suppressed else "cancelled",
            "result": (42 if suppressed else "done") if returned else None,
            "cancel_accepted": external, "reached_end": returned,
            "origin": "external" if external else "none" if case == "no_cancel" else "timer",
            "suppressed": suppressed, "violation": faulty}


def expected_events(policy, case):
    if case == "completed_external":
        return ["inner_start", "inner_result", "outer_start", *(
            ["external_cancel", "wait_returned", "reached_end"] if policy == "before" else
            ["wait_returned", "external_cancel"])]
    if case == "pending_external":
        return ["inner_start", "outer_start", "external_cancel", "inner_cancelled"]
    if case == "no_cancel":
        return ["inner_start", "inner_result", "outer_start", "wait_returned", "reached_end"]
    return ["inner_start", "outer_start", "deadline_fired", "inner_cancelled", *(
        ["inner_suppressed", "wait_returned", "reached_end"] if case == "timeout_suppressed" else [])]


def verified_payloads(root=FIXTURE):
    with (root / "manifest.json").open("rb") as stream:
        raw = stream.read(64 * 1024 + 1)
    if len(raw) > 64 * 1024 or hashlib.sha256(raw).hexdigest() != MANIFEST_SHA256:
        raise ValueError("historical source manifest changed")
    manifest = json.loads(raw)
    if set(manifest["files"]) != FILES:
        raise ValueError("historical source allowlist changed")
    payloads = {"manifest.json": raw}
    for name, pin in manifest["files"].items():
        with (root / name).open("rb") as stream:
            content = stream.read(pin["bytes"] + 1)
        if len(content) != pin["bytes"] or hashlib.sha256(content).hexdigest() != pin["sha256"]:
            raise ValueError(f"historical source identity changed: {name}")
        payloads[name] = content
    return manifest, payloads


def collect_child(command, *, wall_seconds=10, output_bytes=1024**2):
    """Bound both pipes while reading, then kill/reap the disposable process group."""
    started = time.monotonic()
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, start_new_session=True,
                               env={"PATH": "/usr/bin", "LC_ALL": "C.UTF-8"})
    output, errors = bytearray(), bytearray()
    status = "ok"
    try:
        with selectors.DefaultSelector() as selector:
            for stream, target in ((process.stdout, output), (process.stderr, errors)):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, target)
            while selector.get_map():
                remaining = wall_seconds - (time.monotonic() - started)
                if remaining <= 0:
                    status = "wall_timeout"
                    break
                for key, _ in selector.select(min(remaining, 0.1)):
                    block = os.read(key.fd, min(65536, output_bytes - len(output) - len(errors) + 1))
                    if not block:
                        selector.unregister(key.fileobj)
                        continue
                    key.data.extend(block)
                    if len(output) + len(errors) > output_bytes:
                        status = "output_limit"
                        break
                if status != "ok":
                    break
        if status == "ok":
            try:
                process.wait(timeout=max(0.001, wall_seconds - (time.monotonic() - started)))
            except subprocess.TimeoutExpired:
                status = "wall_timeout"
    finally:
        # The leader may have exited successfully while a descendant remains.
        # Always terminate the residual group; the real runner also has a PID namespace.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        process.stdout.close()
        process.stderr.close()
    result = {"status": status, "returncode": process.returncode, "wall_seconds": time.monotonic() - started,
              "stderr": errors.decode("utf-8", errors="replace")[-2000:]}
    if status == "ok" and process.returncode:
        result["status"] = "child_failed"
    elif status == "ok":
        try:
            def unique(pairs):
                value = {}
                for key, item in pairs:
                    if key in value:
                        raise ValueError("duplicate observation key")
                    value[key] = item
                return value
            def invalid_constant(value):
                raise ValueError("non-finite observation number")
            result["observation"] = json.loads(output, object_pairs_hook=unique, parse_constant=invalid_constant)
            if not isinstance(result["observation"], dict):
                raise ValueError("observation must be an object")
        except (ValueError, UnicodeError, RecursionError):
            result["status"] = "malformed_output"
    result["censored"] = result["status"] != "ok"
    return result


def sandbox_command(bwrap, snapshot, policy, case):
    executable, prefix = Path(sys.executable).resolve(), Path(sys.base_prefix).resolve()
    command = [bwrap, "--unshare-all", "--die-with-parent", "--new-session", "--cap-drop", "ALL",
               "--dir", "/usr", "--ro-bind", "/usr/lib", "/usr/lib", "--dir", "/usr/bin",
               "--symlink", "usr/lib", "/lib"]
    if Path("/usr/lib64").exists():
        command += ["--ro-bind", "/usr/lib64", "/usr/lib64", "--symlink", "usr/lib64", "/lib64"]
    if prefix == Path("/usr"):
        command += ["--ro-bind", str(executable), str(executable)]
        interpreter = str(executable)
    else:
        if not executable.is_relative_to(prefix):
            raise ValueError("interpreter is outside its declared base prefix")
        command += ["--ro-bind", str(prefix), "/runtime"]
        interpreter = str(Path("/runtime") / executable.relative_to(prefix))
    return command + ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
                      "--ro-bind", str(snapshot), "/case", "--chdir", "/tmp", "--clearenv",
                      "--setenv", "PATH", "/usr/bin", "--setenv", "LC_ALL", "C.UTF-8",
                      interpreter, "-I", "-S", "-B", "/case/observer.py", policy, case, MANIFEST_SHA256]


def validate_observation(observation, policy, case, parent_netns, expected_runtime):
    """Check identity, shape and protocol preconditions before judging outcomes."""
    if not isinstance(observation, dict) or any(observation.get(key) != value for key, value in (
            ("format", "interlock-waitfor-observation/v1"), ("policy", policy), ("case", case),
            ("manifest_sha256", MANIFEST_SHA256))):
        raise ValueError("wrong observation identity")
    isolation, runtime = observation.get("isolation"), observation.get("runtime")
    if (not isinstance(isolation, dict) or not isinstance(isolation.get("network_namespace"), str)
            or re.fullmatch(r"net:\[\d+\]", isolation["network_namespace"]) is None
            or isolation["network_namespace"] == parent_netns or isolation.get("home_visible") is not False
            or isolation.get("environment") != {"LC_ALL": "C.UTF-8", "PATH": "/usr/bin", "PWD": "/tmp"}):
        raise ValueError("isolation preconditions not established")
    if (not isinstance(runtime, dict) or any(runtime.get(key) != value for key, value in expected_runtime.items())
            or runtime.get("implementation") != "CPython"
            or not isinstance(runtime.get("asyncio_sources"), dict)
            or set(runtime["asyncio_sources"]) != {"tasks", "events", "futures", "exceptions"}
            or any(not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value)
                   for value in runtime["asyncio_sources"].values())):
        raise ValueError("incomplete host runtime evidence")
    fingerprints = [runtime.get("executable_sha256"), *runtime["asyncio_sources"].values()]
    if any(not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value)
           for value in fingerprints):
        raise ValueError("invalid runtime fingerprint")
    limits = runtime.get("rlimits")
    if (not isinstance(limits, dict) or set(limits) != set(RLIMITS)
            or any(not isinstance(pair, list) or len(pair) != 2 or any(type(value) is not int for value in pair)
                   for pair in limits.values()) or limits != RLIMITS):
        raise ValueError("child resource limits differ from the declared caps")
    if observation.get("callback_errors") != [] or type(observation.get("pending_tasks")) is not int or observation["pending_tasks"] != 0:
        raise ValueError("callback errors or unfinished tasks")
    deadlines, fired = observation.get("deadlines"), observation.get("deadlines_fired")
    if (not isinstance(deadlines, list) or len(deadlines) != 1 or not isinstance(deadlines[0], dict)
            or type(deadlines[0].get("id")) is not int or deadlines[0]["id"] != 0
            or deadlines[0].get("callback") != ("_release_waiter" if policy == "before" else "_on_timeout")
            or type(deadlines[0].get("delay")) is not float or not math.isfinite(deadlines[0]["delay"])
            or not 0 < deadlines[0]["delay"] <= (0.02 if case.startswith("timeout") else 100)):
        raise ValueError("deadline provenance preconditions not established")
    if not isinstance(fired, list) or any(type(value) is not int for value in fired) or fired != ([0] if case.startswith("timeout") else []):
        raise ValueError("wrong deadline provenance or unexpected deadline expiry")
    result = observation.get("result")
    if not isinstance(result, dict):
        raise ValueError("missing observed result")
    if case == "upstream":
        if (result.get("outcome") not in ("passed", "assertion_failed") or
                not (result.get("message") is None or isinstance(result.get("message"), str))):
            raise ValueError("malformed upstream assertion outcome")
        return
    projection = expected_projection(policy, case)
    if any(key not in result for key in (*projection, "inner_result")):
        raise ValueError("incomplete observed outcome")
    for key in ("cancel_accepted", "reached_end", "suppressed", "violation"):
        if type(result[key]) is not bool:
            raise ValueError("invalid observed boolean")
    if any(result[key] is not None and type(result[key]) not in (str, int) for key in ("result", "inner_result")):
        raise ValueError("invalid observed result type")
    if any(type(result[key]) is not str for key in ("outer", "inner", "origin")):
        raise ValueError("invalid observed state type")
    if (not isinstance(result.get("events"), list) or any(not isinstance(event, str) for event in result["events"])
            or result["events"] != expected_events(policy, case)
            or type(result.get("external_requests")) is not int
            or result["external_requests"] != int(case.endswith("external"))):
        raise ValueError("missing external cancellation provenance")
    preconditions = result.get("preconditions")
    if (not isinstance(preconditions, dict) or set(preconditions) != {
            "outer_pending_before_cancel", "inner_done_before_cancel", "inner_value_before_cancel"}
            or preconditions.get("outer_pending_before_cancel") is not True
            or preconditions.get("inner_done_before_cancel") is not (case in ("completed_external", "no_cancel"))
            or preconditions.get("inner_value_before_cancel") != ("done" if case in ("completed_external", "no_cancel") else None)
            or result["cancel_accepted"] is not case.endswith("external")):
        raise ValueError("historical cancellation schedule preconditions not established")
    if result.get("inner_result") != ("done" if case in ("completed_external", "no_cancel") else
                                      42 if case == "timeout_suppressed" else None):
        raise ValueError("inner result preservation precondition failed")


def run_calibration(*, model_only=False):
    report = {"format": "interlock-historical-waitfor/v1", "contract": "interlock-cpython-waitfor-86296/v1",
              "status": "incomplete", "model": model_report(), "observations": [],
              "scope": "Historical single-parent calibration. Selected source on a modern host, not the historical CPython build or a four-way merge. Model coverage and observed source schedules are separate.",
              "limits": {"wall_seconds_per_child": 10, "cpu_soft_seconds": 5, "cpu_hard_seconds": 6,
                         "address_space_bytes": 512 * 1024**2, "output_bytes": 1024**2},
              "substitutions": ["Host asyncio Tasks/Futures, events, exceptions and ensure_future; pinned timeout definitions.",
                                "Named upstream assertion body only; its IsolatedAsyncioTestCase lifecycle and other tests are not run.",
                                "Independent observer follows the declared schedule and adds outcome/provenance records."],
              "observations_complete": False}
    for result in report["model"]["results"]:
        if not result["complete"]:
            report["reason"] = "finite model did not exhaust within the frozen caps"
            return report
        if result["calibration"]["projection"] != expected_projection(result["policy"], result["case"]):
            report.update(status="model_mismatch", reason="model disagrees with the frozen observable contract")
            return report
    try:
        manifest, payloads = verified_payloads()
    except (OSError, ValueError) as exc:
        report.update(status="source_drift", reason=str(exc))
        return report
    report["source_identity"] = {"manifest_sha256": MANIFEST_SHA256, "manifest": manifest}
    observer = Path(__file__).with_name("_waitfor_observer.py").read_bytes()
    report["implementation_sha256"] = {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                                       for name in ("historical_waitfor.py", "waitfor_model.py", "_waitfor_observer.py")}
    if model_only:
        report.update(status="model_only", reason="source functions not executed; model evidence only")
        return report
    bwrap = shutil.which("bwrap", path="/usr/bin:/bin")
    if (not sys.platform.startswith("linux") or sys.version_info < (3, 11) or bwrap is None
            or platform.python_implementation() != "CPython"):
        report.update(status="unsupported", reason="source observations require Linux, Python 3.11+ and bubblewrap; no unisolated fallback")
        return report
    parent_netns = os.readlink("/proc/self/ns/net")
    executable_digest = hashlib.sha256()
    with Path(sys.executable).resolve().open("rb") as executable:
        for block in iter(lambda: executable.read(1024**2), b""):
            executable_digest.update(block)
    with tempfile.TemporaryDirectory(prefix="interlock-waitfor-") as directory:
        snapshot = Path(directory)
        (snapshot / "fixture").mkdir()
        for name, content in payloads.items():
            (snapshot / "fixture" / name).write_bytes(content)
        (snapshot / "observer.py").write_bytes(observer)
        for policy in POLICIES:
            for case in ("upstream", *CASES):
                try:
                    command = sandbox_command(bwrap, snapshot, policy, case)
                    expected_runtime = {"python": platform.python_version(), "implementation": "CPython",
                                        "executable": command[command.index("-I") - 1],
                                        "executable_sha256": executable_digest.hexdigest()}
                    outcome = collect_child(command)
                except (OSError, ValueError) as exc:
                    outcome = {"status": "launch_failed", "censored": True, "detail": str(exc)}
                record = {"policy": policy, "case": case, **outcome}
                report["observations"].append(record)
                if outcome["status"] != "ok":
                    report["reason"] = "isolated source observation failed; remaining observations not run"
                    return report
                observed = outcome["observation"]
                try:
                    validate_observation(observed, policy, case, parent_netns, expected_runtime)
                except ValueError as exc:
                    record.update(status="invalid_observation", censored=True, detail=str(exc))
                    report["reason"] = "source observation or protocol preconditions invalid"
                    return report
                if case == "upstream":
                    expected = ({"outcome": "assertion_failed", "message": "CancelledError not raised"} if policy == "before"
                                else {"outcome": "passed", "message": None})
                    matches = observed["result"] == expected
                else:
                    expected = expected_projection(policy, case)
                    matches = {key: observed["result"][key] for key in expected} == expected
                record.update(expected=expected, matches=matches)
                if not matches:
                    report.update(status="expectation_failed", reason="source outcome disagrees with the predeclared calibration contract")
                    return report
    report.update(status="calibrated", observations_complete=True,
                  reason="Two upstream assertion outcomes and ten declared source observations match; no exhaustive source-prefix claim")
    return report
