"""Terminal interface; all inputs and outputs stay in local files."""

import argparse
import json
from pathlib import Path
import sys

from . import __version__
from .engine import make_witness, replay_witness, search
from .fixture import (FIXTURES, check_fixture, replay_fixture, validate_fixture,
                      validate_witness_fixture)
from .scenario import MAX_WITNESS_BYTES, canonical, read_json, validate_scenario


def _write(path: str, value: dict, force: bool = False, *, compact: bool = False,
           max_bytes: int | None = None) -> None:
    payload = (canonical(value) if compact else json.dumps(value, indent=2, sort_keys=True)) + "\n"
    if max_bytes is not None and len(payload.encode("utf-8")) > max_bytes:
        raise ValueError(f"output exceeds {max_bytes / 1_000_000:g} MB limit")
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w" if force else "x", encoding="utf-8") as stream:
        stream.write(payload)


def _validate_outputs(source: str, outputs: list[str], force: bool) -> None:
    paths = [Path(source), *(Path(path) for path in outputs)]
    for index, path in enumerate(paths):
        for other in paths[:index]:
            if path.resolve() == other.resolve() or (path.exists() and other.exists() and path.samefile(other)):
                raise ValueError("input, report and witness must be different files")
    for path in paths[1:]:
        if path.is_symlink():
            raise ValueError(f"refusing symlink output: {path}")
        if path.exists() and not force:
            raise ValueError(f"output already exists: {path}; choose a fresh path or use --force")


def _show_report(report: dict) -> None:
    print(f"Interlock · {report['name']}")
    print(f"Result: {report['status']}")
    coverage = report["coverage"]
    print(f"Explored {coverage['states_explored']} product states, "
          f"{coverage['transitions_explored']} transitions; "
          f"event bound {report['bounds']['max_depth']}.")
    print(f"Search complete within bound: {str(coverage['complete_up_to_depth']).lower()}")
    for version, outcome in report["versions"].items():
        passed = outcome["passed_explored_states"]
        print(f"  {version:6} {'PASS in explored states' if passed else 'FAIL'}")
    if report["candidate"]:
        print("Shortest interaction candidate:")
        print("  " + " → ".join(report["candidate"]["events"]))
        for version, outcome in report["candidate"]["outcomes"].items():
            print(f"  {version:6} {json.dumps(outcome['state'], sort_keys=True)}")
    print(report["scope"])
    if "fixture" in report:
        checked = report["fixture"]
        print(f"Bundled fixture {checked['fixture']}: {checked['status']}")
        if "coverage" in checked:
            print(f"  Checked {checked['coverage']['schedules_checked']} legal schedule prefixes; "
                  f"complete within bound: {str(checked['coverage']['complete_up_to_depth']).lower()}")
        if checked.get("first_mismatch"):
            _show_fixture(checked["first_mismatch"])
        elif checked.get("candidate_replay"):
            print("  Actual recorded effects: " + ", ".join(
                f"{version}={len(outcome['effect_records'])}"
                for version, outcome in checked["candidate_replay"]["observed_outcomes"].items()))


def _show_fixture(result):
    print(f"Bundled fixture agreement: {str(result['agreement']).lower()}")
    print(f"Observed interaction reproduced: {str(result['interaction_reproduced']).lower()}")
    for item in result["trace"]:
        print(f"{item['step']:2} {item['event'] or '(initial)'}")
        for version, outcome in item["observed"].items():
            print(f"   {version:6} {json.dumps(outcome['state'], sort_keys=True)} "
                  f"effects={len(outcome['effect_records'])} clock={outcome['clock']}")
        for mismatch in item["mismatches"]:
            print(f"   MISMATCH {mismatch['version']}.{mismatch['field']}: "
                  f"expected {mismatch['expected']!r}; observed {mismatch['observed']!r}")
    print(result["scope"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Find bounded behavioral merge interactions in explicit models.")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="Explore base, left, right, and merged together")
    check.add_argument("scenario")
    check.add_argument("--max-depth", type=int, default=8)
    check.add_argument("--max-states", type=int, default=50_000)
    check.add_argument("--json", action="store_true", help="Print machine-readable report")
    check.add_argument("--report", help="Also write JSON report to this local file")
    check.add_argument("--witness", help="Write shortest candidate witness if one is found")
    check.add_argument("--force", action="store_true", help="Allow replacement of existing output files")
    check.add_argument("--fixture", choices=sorted(FIXTURES),
                       help="Opt in to checking trusted bundled handlers against every bounded legal schedule prefix")
    reproduce = commands.add_parser("replay", help="Replay a self-contained witness")
    reproduce.add_argument("witness")
    reproduce.add_argument("--json", action="store_true")
    replay_mode = reproduce.add_mutually_exclusive_group()
    replay_mode.add_argument("--fixture", choices=sorted(FIXTURES),
                           help="Opt in to replaying this witness against trusted bundled handlers")
    replay_mode.add_argument("--model-only", action="store_true",
                             help="Replay only the embedded model, without checking pinned fixture sources")
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            _validate_outputs(args.scenario, [path for path in (args.report, args.witness) if path], args.force)
            scenario = validate_scenario(read_json(args.scenario))
            if args.fixture:
                validate_fixture(scenario, args.fixture)
            report = search(scenario, args.max_depth, args.max_states)
            witness_allowed = report["candidate"] is not None
            if args.fixture:
                report["model_status"] = report["status"]
                if report["status"] == "incomplete":
                    report["fixture"] = {"fixture": args.fixture, "status": "not_run",
                                         "reason": "Model search exceeded its state budget."}
                    witness_allowed = False
                else:
                    report["fixture"] = check_fixture(scenario, args.fixture, max_depth=args.max_depth)
                    fixture_status = report["fixture"]["status"]
                    if fixture_status != "agreement":
                        report["status"] = fixture_status
                        witness_allowed = False
                    elif report["candidate"]:
                        report["fixture"]["candidate_replay"] = replay_fixture(
                            scenario, report["candidate"]["events"], args.fixture)
            if args.witness and not witness_allowed and Path(args.witness).exists():
                raise ValueError("no verified candidate available; refusing to leave an existing witness that describes an older run")
            if args.report:
                _write(args.report, report, args.force)
            if args.witness and witness_allowed:
                _write(args.witness, make_witness(scenario, report), args.force,
                       compact=True, max_bytes=MAX_WITNESS_BYTES)
            if args.json:
                print(json.dumps(report, indent=2, sort_keys=True))
            else:
                _show_report(report)
                if args.witness and not witness_allowed:
                    print("No witness written: no verified candidate is available within the requested scope.")
            if report["status"] == "fixture_mismatch":
                return 4
            return 3 if report["status"] == "incomplete" else int(report["status"] != "no_interaction_within_bound")
        witness = read_json(args.witness, max_bytes=MAX_WITNESS_BYTES)
        result = replay_witness(witness)
        if "fixture" in witness and not (args.fixture or args.model_only):
            raise ValueError(f"this witness pins fixture {witness['fixture']['name']!r}; "
                             f"use --fixture {witness['fixture']['name']} or --model-only")
        if args.fixture:
            provenance = validate_witness_fixture(witness, args.fixture)
            result = replay_fixture(witness["scenario"], witness["events"], args.fixture)
            result["source_verification"] = provenance
            if args.json:
                print(json.dumps(result, indent=2, sort_keys=True))
            else:
                print("Fixture source identity: " + provenance)
                _show_fixture(result)
            return 4 if not result["agreement"] else int(any(
                not outcome["passed"] for outcome in result["observed_outcomes"].values()))
        result["execution_scope"] = "model_only"
        if "fixture" in witness:
            result["source_verification"] = "not_checked"
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            if "fixture" in witness:
                print("Model-only replay: pinned fixture sources were not checked or executed.")
            print(f"Interaction reproduced: {str(result['interaction_reproduced']).lower()}")
            for item in result["trace"]:
                print(f"{item['step']:2} {item['event'] or '(initial)'}")
                for version, outcome in item["outcomes"].items():
                    stutter = " (event disabled; unchanged)" if version in item["stuttered"] else ""
                    print(f"   {version:6} {json.dumps(outcome['state'], sort_keys=True)}{stutter}")
            print("Replay covers this event sequence only; it does not recheck the full search bound.")
        return int(any(not outcome["passed"] for outcome in result["outcomes"].values()))
    except (ValueError, OSError, UnicodeError, RecursionError) as exc:
        print(f"interlock: {exc}", file=sys.stderr)
        return 2
