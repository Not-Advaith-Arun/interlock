"""Terminal interface; all inputs and outputs stay in local files."""

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

from . import __version__
from .engine import make_witness, replay_witness
from .fixture import (FIXTURES, MAX_FIXTURE_SCHEDULES, fixture_catalog,
                      fixture_scenario, replay_fixture, validate_witness_fixture)
from .scenario import MAX_WITNESS_BYTES, canonical, read_json, validate_scenario
from .runner import run_check
from .suite import EXIT_CODES as SUITE_EXIT_CODES, EXPECTED_WITNESSES, run_suite


def _write(path: str, value: dict, force: bool = False, *, compact: bool = False,
           max_bytes: int | None = None) -> None:
    payload = (canonical(value) if compact else json.dumps(value, indent=2, sort_keys=True)) + "\n"
    if max_bytes is not None and len(payload.encode("utf-8")) > max_bytes:
        raise ValueError(f"output exceeds {max_bytes / 1_000_000:g} MB limit")
    _write_payload(path, payload, force)


def _write_payload(path: str, payload: str, force: bool = False) -> None:
    destination = Path(path)
    if destination.is_symlink():
        raise ValueError(f"refusing symlink output: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp",
                                             dir=destination.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if force:
            os.replace(temporary, destination)
        else:
            # An exclusive hard link publishes the complete file and refuses a
            # destination created after preflight. Both paths share a directory.
            os.link(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _validate_outputs(source: str | None, outputs: list[str], force: bool) -> None:
    paths = ([Path(source)] if source else []) + [Path(path) for path in outputs]
    for index, path in enumerate(paths):
        for other in paths[:index]:
            if path.resolve() == other.resolve() or (path.exists() and other.exists() and path.samefile(other)):
                raise ValueError("input, report and witness must be different files")
    for path in map(Path, outputs):
        if path.is_symlink():
            raise ValueError(f"refusing symlink output: {path}")
        if path.exists() and not path.is_file():
            raise ValueError(f"output must be a regular file: {path}")
        parent = path.parent
        while not parent.exists() and parent != parent.parent:
            parent = parent.parent
        if not parent.is_dir():
            raise ValueError(f"output parent must be a directory: {parent}")
        if path.exists() and not force:
            raise ValueError(f"output already exists: {path}; choose a fresh path or use --force")


def _replay_summary(witness, result, *, fixture=False):
    outcomes = result["observed_outcomes"] if fixture else result["outcomes"]
    return {"scenario_sha256": witness["scenario_sha256"], "event_count": len(witness["events"]),
            "interaction_reproduced": result["interaction_reproduced"],
            "execution_scope": "bundled_handlers" if fixture else "model_only",
            "source_verification": result.get("source_verification", "not_checked"),
            **({"agreement": result["agreement"]} if fixture else {}),
            "versions": {name: {"passed": row["passed"], "violations": row["violations"]}
                         for name, row in outcomes.items()},
            "scope": "Full requested replay performed; detailed states and trace omitted from this summary. This event sequence only, not full search bounds, global branch safety or shortest failure. Output reduction does not bound replay cost."}


def _terminal_text(text: str) -> str:
    """Keep untrusted titles/diagnostics from emitting C0/C1 terminal controls."""
    return "".join(f"\\x{ord(character):02x}" if (ord(character) < 32 and character not in "\t\n")
                   or 127 <= ord(character) <= 159 else character for character in text)


def _show_report(report: dict) -> None:
    print(_terminal_text(f"Interlock · {report['name']}"))
    print(f"Result: {report['status']}")
    coverage = report["coverage"]
    print(f"Explored {coverage['states_explored']} product states, "
          f"{coverage['transitions_explored']} transitions; "
          f"event bound {report['bounds']['max_depth']}.")
    print(f"Search complete within bound: {str(coverage['complete_up_to_depth']).lower()}")
    print(f"Model exploration stopped: {coverage['termination_reason']}")
    for version, outcome in report["versions"].items():
        passed = outcome["passed_explored_states"]
        print(f"  {version:6} {'PASS in explored states' if passed else 'FAIL'}")
    if report["candidate"]:
        print("Shortest schedule-local interaction candidate (independent branch status above still applies):")
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
            print(f"  Handler exploration stopped: {checked['coverage']['termination_reason']}")
        if checked.get("reason"):
            print(f"  {checked['reason']}")
        for version, failure in checked.get("failure_replays", {}).items():
            failed = [name for name, outcome in failure["observed_outcomes"].items() if not outcome["passed"]]
            print(f"  Direct {version} failure replay agrees: {str(failure['agreement']).lower()}; "
                  f"failed versions: {', '.join(failed)} (this schedule only)")
        if checked.get("envelope_probe"):
            probe = checked["envelope_probe"]
            print(f"  Frozen direct probe within requested search depth: {str(probe['within_search_depth']).lower()}; "
                  f"known unsafe versions: {', '.join(checked['known_unsafe_versions']) or 'none in this probe'}")
            print("  " + checked["branch_safety_caveat"])
        case = checked.get("case", {})
        if case.get("issue"):
            print(f"  Historical failure reconstruction; synthetic branch split: {case['issue']}")
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
            if "completion_causes" in outcome["state"]:
                for cause in outcome["state"]["completion_causes"]:
                    print(f"            {cause['acknowledgement_id']} → completed {cause['job_id']}")
        for mismatch in item["mismatches"]:
            print(f"   MISMATCH {mismatch['version']}.{mismatch['field']}: "
                  f"expected {mismatch['expected']!r}; observed {mismatch['observed']!r}")
    print(result["scope"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Find bounded behavioral merge interactions in explicit models.",
        epilog="Exit codes: 0 no failure within scope or expected suite results; 1 failure found or suite expectation failed; 2 invalid input or file error; "
               "3 incomplete exploration; 4 model/handler mismatch.")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    from .showcase import arguments as showcase_arguments
    showcase_arguments(commands.add_parser("showcase", help="generate an interactive offline product sample"))
    historical = commands.add_parser("historical-waitfor", help="Calibrate a pinned CPython before/fix pair separately from merge checking")
    historical.add_argument("--model-only", action="store_true", help="Run only the finite decision model; do not execute selected historical functions")
    historical.add_argument("--html",action="store_true",help="Captured metadata cards; cannot combine with JSON or report export")
    historical.add_argument("--json", action="store_true")
    historical.add_argument("--report", help="Write the versioned local calibration report")
    historical.add_argument("--force", action="store_true", help="Allow replacement of an existing report")
    catalog = commands.add_parser("fixtures", help="List bundled runnable cases and passing controls")
    catalog.add_argument("--json", action="store_true")
    example = commands.add_parser("example", help="Generate a scenario for a bundled fixture")
    example.add_argument("fixture", choices=sorted(FIXTURES))
    example.add_argument("--output", help="Write JSON to this file instead of standard output")
    example.add_argument("--force", action="store_true", help="Allow replacement of an existing output")
    check = commands.add_parser("check", help="Explore base, left, right, and merged together")
    check.add_argument("scenario")
    check.add_argument("--profile", action="store_true", help="Record checker wall/CPU and process-lifetime Linux peak RSS")
    check.add_argument("--max-depth", type=int, default=8)
    check.add_argument("--max-states", type=int, default=50_000)
    check.add_argument("--max-schedules", type=int,
                       help=f"Fixture prefix budget, 1..{MAX_FIXTURE_SCHEDULES} (default: {MAX_FIXTURE_SCHEDULES}; requires --fixture)")
    check.add_argument("--json", action="store_true", help="Print machine-readable report")
    check.add_argument("--report", help="Also write JSON report to this local file")
    check.add_argument("--witness", help="Write shortest candidate witness if one is found")
    check.add_argument("--force", action="store_true", help="Allow replacement of existing output files")
    check.add_argument("--fixture", choices=sorted(FIXTURES),
                       help="Opt in to checking trusted bundled handlers against every bounded legal schedule prefix")
    witness_cases=commands.add_parser("match-witness-cases",help="Match witness canonical scenario identity to complete explicit case declarations without replay, outcomes or source verification")
    witness_cases.add_argument("witness",type=Path)
    witness_cases.add_argument("manifest",type=Path)
    witness_cases.add_argument("--html",action="store_true")
    binding=commands.add_parser("inspect-case-binding",help="Compare retained recorded case identities/expectations against explicit declarations; no execution or authentication")
    binding.add_argument("manifest",type=Path)
    binding.add_argument("report",type=Path)
    binding.add_argument("--case",action="append")
    binding.add_argument("--html",action="store_true")
    depth_compare=commands.add_parser("compare-case-depths",help="Compare complete recorded case/depth matrices and coverage without executing models")
    depth_compare.add_argument("before",type=Path)
    depth_compare.add_argument("after",type=Path)
    depth_compare.add_argument("--html",action="store_true")
    case_compare = commands.add_parser("compare-case-results", help="Compare recorded model case classifications without replay, execution or safety judgment")
    case_compare.add_argument("before")
    case_compare.add_argument("after")
    case_compare.add_argument("--include-coverage",action="store_true",help="Also compare recorded requested model bounds and coverage counters; no rerun/authentication")
    case_compare.add_argument("--html", action="store_true", help="Offline recorded metadata comparison; no replay or safety claim")
    from .case_template import REFERENCE_EXPECTATIONS
    manifest_combine=commands.add_parser("combine-case-manifests",help="Combine explicit regression declarations without overwriting conflicting IDs or running tests")
    manifest_combine.add_argument("left",type=Path)
    manifest_combine.add_argument("right",type=Path)
    manifest_combine.add_argument("--html",action="store_true")
    manifest_comparison=commands.add_parser("compare-case-manifests",help="Compare declared expectations/scenario identities without search or handler execution")
    manifest_comparison.add_argument("left",type=Path)
    manifest_comparison.add_argument("right",type=Path)
    manifest_comparison.add_argument("--html",action="store_true")
    case_picker=commands.add_parser("case-picker",help="Create an explicitly private offline case picker with full caller scenarios and native chosen-manifest export; no execution")
    case_picker.add_argument("input",type=Path)
    case_selection=commands.add_parser("select-cases",help="Export explicitly selected regression declarations in original order without execution")
    case_selection.add_argument("input",type=Path)
    case_selection.add_argument("--case",action="append",required=True)
    case_selection.add_argument("--html",action="store_true",help="Contains full private selected scenarios and native manifest download")
    case_inspection=commands.add_parser("inspect-cases",help="Validate a complete case manifest without running search or handlers")
    case_inspection.add_argument("input",type=Path)
    case_inspection.add_argument("--case",action="append")
    case_inspection.add_argument("--html",action="store_true")
    case_template_parser=commands.add_parser("case-template",help="Draft a model regression manifest from explicit bundled references; frozen expectations, no search/handlers executed")
    case_template_parser.add_argument("--fixture",action="append",choices=sorted(REFERENCE_EXPECTATIONS),required=True,help="Select1..8 unique references, repeat explicitly; expected failures are not safety success")
    case_template_parser.add_argument("--html",action="store_true",help="Inspect reference metadata and download the full native manifest; includes bundled scenario definitions")
    depth_combine = commands.add_parser("combine-case-depths", help="Combine compatible complete retained depth slices without dropping conflicting claims or executing models")
    depth_combine.add_argument("left")
    depth_combine.add_argument("right")
    depth_combine.add_argument("--html", action="store_true")
    depth_select = commands.add_parser("select-case-depths", help="Extract explicit cases from a fully validated retained matrix, preserving every recorded depth without execution")
    depth_select.add_argument("report")
    depth_select.add_argument("--case", action="append", required=True)
    depth_select.add_argument("--html", action="store_true")
    depth_summary=commands.add_parser("case-depth-summary",help="Summarize retained complete/incomplete bounds separately without search, interpolation or safety claims")
    depth_summary.add_argument("report",type=Path)
    depth_summary.add_argument("--html",action="store_true")
    depth_template_parser=commands.add_parser("case-depth-template",help="Choose bounded case/depth settings under a complete declaration guard without executing models")
    depth_template_parser.add_argument("manifest",type=Path)
    depth_template_parser.add_argument("--json",action="store_true")
    case_depths=commands.add_parser("check-case-depths",help="Run explicit model case regressions independently at several bounded depths; preserve per-depth coverage/expectations")
    case_depths.add_argument("manifest",type=Path)
    depth_input=case_depths.add_mutually_exclusive_group(required=True)
    depth_input.add_argument("--depth",type=int,action="append")
    depth_input.add_argument("--plan",type=Path)
    case_depths.add_argument("--case",action="append")
    case_depths.add_argument("--max-states",type=int,help="Manual per-cell budget; default5000, incompatible with captured --plan")
    case_depths.add_argument("--html",action="store_true")
    cases = commands.add_parser("check-cases", help="Run a caller-authored bounded model regression manifest with expected classifications")
    cases.add_argument("manifest",help="Local manifest file or - for bounded JSON stdin")
    cases.add_argument("--case", action="append", help="Run only these existing case IDs; full manifest still validates")
    cases.add_argument("--max-depth", type=int, default=8)
    cases.add_argument("--max-states", type=int, default=25000)
    case_output=cases.add_mutually_exclusive_group()
    case_output.add_argument("--summary", action="store_true", help="Print classification summary only; --report still saves complete evidence")
    case_output.add_argument("--html", action="store_true", help="Offline classification review after bounded model search; failure/incomplete exit codes preserved")
    cases.add_argument("--report")
    cases.add_argument("--force", action="store_true")
    batch = commands.add_parser("check-many", help="Check1..8 explicit scenario files in model-only scope with separate coverage and bounded total requested states")
    batch.add_argument("scenarios", nargs="+")
    batch.add_argument("--html",action="store_true",help="Model-only classification/bounds/coverage cards; full evidence stays in JSON/--report")
    batch.add_argument("--max-depth", type=int, default=8)
    batch.add_argument("--max-states", type=int, default=25000, help="Per-scenario ceiling; selected count times ceiling must be<=200000")
    batch.add_argument("--report", help="Atomically save full per-scenario model reports")
    batch.add_argument("--force", action="store_true")
    suite = commands.add_parser("suite", help="Verify the eight complete bundled conflict/control cases in real handlers")
    suite.add_argument("--fixture", action="append", choices=sorted(EXPECTED_WITNESSES),
                       help="Check only this fixture (repeat to select several; default: all)")
    suite.add_argument("--max-depth", type=int, default=12,
                       help="Event bound; suite success requires exhausting finite fixtures (default: 12)")
    suite.add_argument("--max-states", type=int, default=50_000)
    suite.add_argument("--max-schedules", type=int, default=MAX_FIXTURE_SCHEDULES)
    suite.add_argument("--json", action="store_true")
    suite.add_argument("--html",action="store_true",help="Captured bundled-handler suite verdict/coverage cards; executes the requested suite")
    suite.add_argument("--summary", action="store_true", help="Emit compact JSON verdicts/coverage after full execution; --report still saves complete diagnostics")
    suite.add_argument("--report", help="Also write the full suite report to this file")
    suite.add_argument("--force", action="store_true", help="Allow replacement of an existing report")
    reproduce = commands.add_parser("replay", help="Replay a self-contained witness")
    reproduce.add_argument("witness")
    reproduce.add_argument("--json", action="store_true")
    reproduce.add_argument("--require-pin", action="store_true", help="Require verified source binding before trusted handler execution; requires --fixture")
    reproduce.add_argument("--trace-limit", type=int, help="Return1..1000 trace frames as JSON after full requested replay; preserve final outcomes")
    reproduce.add_argument("--from-step", type=int, default=0, help="Inclusive original trace-step cursor for --trace-limit;0 includes initial state")
    reproduce.add_argument("--summary", action="store_true", help="Emit compact JSON outcomes without detailed trace/state; perform the same full requested replay")
    replay_mode = reproduce.add_mutually_exclusive_group()
    replay_mode.add_argument("--fixture", choices=sorted(FIXTURES),
                           help="Opt in to replaying this witness against trusted bundled handlers")
    replay_mode.add_argument("--model-only", action="store_true",
                             help="Replay only the embedded model, without checking pinned fixture sources")
    prefix = commands.add_parser("replay-prefix", help="Execute only an explicit witness prefix; remaining event legality/outcomes are not checked")
    prefix.add_argument("witness")
    prefix.add_argument("--html",action="store_true",help="Captured prefix outcome metadata only; requires --model-only")
    prefix.add_argument("--through-step", type=int, required=True, help="Inclusive event count;0 executes initial state only")
    prefix.add_argument("--require-pin", action="store_true")
    prefix_mode = prefix.add_mutually_exclusive_group(required=True)
    prefix_mode.add_argument("--model-only", action="store_true")
    prefix_mode.add_argument("--fixture", choices=sorted(FIXTURES))
    sweep = commands.add_parser("sweep-depths", help="Compare bounded model/optional bundled-handler checks at selected depths")
    sweep.add_argument("scenario")
    sweep.add_argument("--html",action="store_true",help="Metadata-only bounded search cards; requires --model-only")
    sweep.add_argument("--depth", type=int, action="append", required=True)
    sweep.add_argument("--max-states", type=int, default=5000)
    sweep.add_argument("--profile", action="store_true", help="Measure each search on Linux; RSS is the process-lifetime high-water mark")
    sweep_mode = sweep.add_mutually_exclusive_group(required=True)
    sweep_mode.add_argument("--model-only", action="store_true")
    sweep_mode.add_argument("--fixture", choices=sorted(FIXTURES), help="Explicit trusted bundled handlers, checked at each bound")
    sweep.add_argument("--max-schedules", type=int, help="Per-depth handler prefix budget; requires --fixture")
    scenarios = commands.add_parser("compare-scenarios", help="Compare declared configuration changes without executing or assessing safety")
    scenarios.add_argument("left")
    scenarios.add_argument("right")
    scenarios.add_argument("--html", action="store_true", help="Captured declared differences only; no search or execution")
    inspection = commands.add_parser("inspect-witness", help="Inspect witness structure/counts/fingerprints without replay or source verification")
    inspection.add_argument("witness")
    inspection.add_argument("--html", action="store_true", help="Offline structural intake only; no replay or source verification")
    comparison = commands.add_parser("compare-witnesses", help="Compare two validated schedules with explicit model or trusted bundled-handler scope")
    comparison.add_argument("left")
    comparison.add_argument("right")
    comparison.add_argument("--html", action="store_true", help="Requires --structure-only; no model or handler execution")
    comparison.add_argument("--require-pin", action="store_true", help="Require both verified source bindings; requires --fixture")
    compare_mode = comparison.add_mutually_exclusive_group(required=True)
    compare_mode.add_argument("--model-only", action="store_true")
    compare_mode.add_argument("--structure-only", action="store_true", help="Compare validated event positions without replay, event names or safety outcomes")
    compare_mode.add_argument("--fixture", choices=sorted(FIXTURES), help="Opt in to both schedules' trusted bundled handlers; imported code is never executed")
    minimize = commands.add_parser("minimize", help="Reduce an imported trace with explicit model-only or pinned bundled-handler scope")
    minimize.add_argument("witness")
    reduction_mode = minimize.add_mutually_exclusive_group(required=True)
    reduction_mode.add_argument("--fixture", choices=sorted(FIXTURES), help="Verify pinned source identity and reduce against trusted bundled handlers")
    reduction_mode.add_argument("--model-only", action="store_true",
                          help="Acknowledge that pinned sources and actual handlers will not be checked")
    minimize.add_argument("--max-attempts", type=int, default=500)
    minimize.add_argument("--max-diagnostics", type=int, default=0, help="Retain the first 0..1000 removal decisions without changing reduction")
    minimize.add_argument("--html", action="store_true", help="Read-only model reduction metadata; no witness or diagnostic export")
    minimize.add_argument("--json", action="store_true")
    minimize.add_argument("--report", help="Write a diagnostic report, not a publishable witness")
    minimize.add_argument("--model-witness", help="Export a replayable v1 witness only after complete reduction; requires --model-only and makes no source verification claim")
    minimize.add_argument("--force", action="store_true")
    view = commands.add_parser("view-witness", help="Export a static four-version replay review as HTML to stdout")
    view.add_argument("witness")
    view_mode = view.add_mutually_exclusive_group(required=True)
    view_mode.add_argument("--model-only", action="store_true")
    view_mode.add_argument("--fixture", choices=sorted(FIXTURES))
    view.add_argument("--require-pin", action="store_true", help="Require verified source binding before HTML handler replay; requires --fixture")
    view.add_argument("--max-frames", type=int, default=100)
    view.add_argument("--output", help="Atomically save HTML to a distinct local file instead of stdout")
    view.add_argument("--force", action="store_true", help="Allow replacement of an existing HTML file")
    args = parser.parse_args(argv)
    if args.command == "showcase":
        from .showcase import generate
        return generate(args)
    try:
        if args.command == "replay":
            if args.trace_limit is not None:
                if not args.json or args.summary or not 1 <= args.trace_limit <= 1000 or not 0 <= args.from_step <= 1001:
                    raise ValueError("trace paging requires --json, no --summary, trace limit1..1000 and from step0..1001")
            elif args.from_step:
                raise ValueError("--from-step requires --trace-limit")
        if getattr(args, "require_pin", False) and not args.fixture:
            raise ValueError("--require-pin requires --fixture")
        if args.command == "replay-prefix":
            if args.html and not args.model_only:
                raise ValueError("prefix HTML requires --model-only; use explicit JSON for handler replay")
            from .prefix_replay import replay_prefix
            result = replay_prefix(read_json(args.witness, max_bytes=MAX_WITNESS_BYTES), args.through_step,
                                   fixture=args.fixture, require_pin=args.require_pin)
            if args.html:
                from .prefix_view import render_prefix
                print(render_prefix(result))
            else:
                print(json.dumps(result, indent=2, sort_keys=True))
            replayed = result["result"]
            if args.fixture and not replayed["agreement"]:
                return 4
            outcomes = replayed["observed_outcomes"] if args.fixture else replayed["outcomes"]
            return int(any(not row["passed"] for row in outcomes.values()))
        if args.command == "sweep-depths":
            if args.html and not args.model_only:
                raise ValueError("HTML depth review requires --model-only; use JSON for explicit handler execution")
            from .depth_sweep import sweep_depths
            result = sweep_depths(read_json(args.scenario), args.depth, args.max_states, profile=args.profile,
                                  fixture=args.fixture, max_schedules=args.max_schedules)
            if args.html:
                from .bounded_search_view import render_search
                print(render_search(result,"depth_sweep"))
            else:
                print(json.dumps(result, indent=2, sort_keys=True))
            return 3 if result["any_incomplete"] else 1 if result["any_failure"] else 0
        if args.command == "compare-scenarios":
            from .scenario_comparison import compare_scenarios
            result = compare_scenarios(read_json(args.left), read_json(args.right))
            if args.html:
                from .scenario_view import render_scenarios
                print(render_scenarios(result))
            else:
                print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if args.command == "inspect-witness":
            from .witness_inspection import inspect_witness
            result = inspect_witness(read_json(args.witness,max_bytes=MAX_WITNESS_BYTES))
            if args.html:
                from .preflight_view import render_preflight
                print(render_preflight(result))
            else:
                print(json.dumps(result,indent=2,sort_keys=True))
            return 0
        if args.command == "compare-witnesses":
            if args.html and not args.structure_only:
                raise ValueError("HTML preflight requires --structure-only; use explicit JSON replay for execution")
            from .witness_comparison import compare_witnesses, compare_witness_structure
            if args.structure_only and args.require_pin:
                raise ValueError("source pin requirement needs a fixture replay")
            left = read_json(args.left, max_bytes=MAX_WITNESS_BYTES)
            right = read_json(args.right, max_bytes=MAX_WITNESS_BYTES)
            result = (compare_witness_structure(left, right) if args.structure_only else
                      compare_witnesses(left, right, fixture=args.fixture, require_pin=args.require_pin))
            if args.html:
                from .preflight_view import render_preflight
                print(render_preflight(result))
            else:
                print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if args.command == "view-witness":
            from .witness_view import render_witness
            _validate_outputs(args.witness, [args.output] if args.output else [], args.force)
            witness = read_json(args.witness, max_bytes=MAX_WITNESS_BYTES)
            result = replay_witness(witness)
            if args.fixture:
                provenance = validate_witness_fixture(witness, args.fixture)
                if args.require_pin and provenance != "verified":
                    raise ValueError("source-pinned witness required by --require-pin")
                result = replay_fixture(witness["scenario"], witness["events"], args.fixture)
                result["source_verification"] = provenance
                result["execution_scope"] = "bundled_handlers"
            else:
                result.update(execution_scope="model_only", source_verification="not_checked",
                              scope="Declared model replay only; no source pin or executable handlers checked.")
            html = render_witness(witness["scenario"]["name"], result, max_frames=args.max_frames)
            if args.output:
                _write_payload(args.output, html + "\n", args.force)
                print(f"Wrote HTML review to {args.output}")
            else:
                print(html)
            return 4 if result.get("agreement") is False else 0
        if args.command == "minimize":
            from .reduction import reduce_witness
            if args.html and (not args.model_only or args.json or args.report or args.model_witness):
                raise ValueError("reduction HTML requires --model-only and no JSON/report/witness export")
            if args.model_witness and not args.model_only:
                raise ValueError("model witness export requires explicit --model-only")
            _validate_outputs(args.witness, [p for p in (args.report, args.model_witness) if p], args.force)
            witness = read_json(args.witness, max_bytes=MAX_WITNESS_BYTES)
            result = reduce_witness(witness, args.max_attempts, fixture=args.fixture, max_diagnostics=args.max_diagnostics)
            exported = None
            if args.model_witness and result["one_event_deletion_minimal"]:
                exported = {"format": "interlock-witness-v1", "scenario": witness["scenario"],
                            "scenario_sha256": result["scenario_sha256"], "events": result["reduced_events"]}
                if not replay_witness(exported)["interaction_reproduced"]:
                    raise ValueError("reduced model witness no longer reproduces the interaction")
                if len((canonical(exported) + "\n").encode("utf-8")) > MAX_WITNESS_BYTES:
                    raise ValueError("reduced model witness exceeds the witness byte limit")
            if args.report:
                _write(args.report, result, args.force)
            if exported is not None:
                _write(args.model_witness, exported, args.force, compact=True, max_bytes=MAX_WITNESS_BYTES)
            if args.html:
                from .reduction_view import render_reduction
                print(render_reduction(result))
            elif args.json:
                print(json.dumps(result, indent=2, sort_keys=True))
            else:
                print(f"Trace reduction: {result['status']}; removed {result['removed_events']} events "
                      f"in {result['attempts']} attempts.")
                print("  " + " → ".join(result["reduced_events"]))
                print(result["scope"])
            return 4 if result["status"] == "fixture_mismatch" else 0 if result["one_event_deletion_minimal"] else 3
        if args.command == "historical-waitfor":
            from .historical_waitfor import EXIT_CODES, run_calibration
            if args.html and (args.json or args.report):
                raise ValueError("calibration HTML cannot combine with JSON or report export")
            _validate_outputs(None, [args.report] if args.report else [], args.force)
            result = run_calibration(model_only=args.model_only)
            if args.report:
                _write(args.report, result, args.force)
            if args.html:
                from .calibration_view import render_calibration
                print(render_calibration(result))
            elif args.json:
                print(json.dumps(result, indent=2, sort_keys=True))
            else:
                print(f"Historical before/fix calibration: {result['status']}")
                print(result["reason"])
                print(f"Observed source schedules: {len(result['observations'])}; finite model environments: {len(result['model']['results'])}.")
                print(result["scope"])
            return EXIT_CODES[result["status"]]
        if args.command == "fixtures":
            catalog = fixture_catalog()
            if args.json:
                print(json.dumps(catalog, indent=2, sort_keys=True))
            else:
                print("Bundled fixtures (default bounds):")
                for fixture in catalog["fixtures"]:
                    print(f"  {fixture['name']:24} {fixture['model']:18} {fixture['expected_status']}")
                print("Start with: interlock example cancellation-conflict --output scenario.json")
                print("Then: interlock check scenario.json --fixture cancellation-conflict --witness witness.json")
                print("Replay: interlock replay witness.json --fixture cancellation-conflict")
            return 0
        if args.command == "example":
            scenario = fixture_scenario(args.fixture)
            if args.output:
                _validate_outputs(None, [args.output], args.force)
                _write(args.output, scenario, args.force)
                print(f"Scenario written: {args.output}")
            else:
                print(json.dumps(scenario, indent=2, sort_keys=True))
            return 0
        if args.command == "match-witness-cases":
            from .witness_case_match import match_witness_cases,render_witness_case_match
            result=match_witness_cases(read_json(args.witness,max_bytes=MAX_WITNESS_BYTES),read_json(args.manifest))
            print(render_witness_case_match(result)if args.html else json.dumps(result,indent=2))
            return 0 if result['matched']else 1
        if args.command == "combine-case-depths":
            from .depth_selection import combine_depth_cases
            from .case_depths import render_case_depths
            result = combine_depth_cases(read_json(args.left), read_json(args.right))
            print(render_case_depths(result) if args.html else json.dumps(result, indent=2))
            return 0
        if args.command == "select-case-depths":
            from .depth_selection import select_depth_cases
            from .case_depths import render_case_depths
            result = select_depth_cases(read_json(args.report), args.case)
            print(render_case_depths(result) if args.html else json.dumps(result, indent=2))
            return 0
        if args.command == "case-depth-summary":
            from .depth_summary import summarize_depths,render_depth_summary
            result=summarize_depths(read_json(args.report))
            print(render_depth_summary(result)if args.html else json.dumps(result,indent=2))
            return 0
        if args.command == "case-depth-template":
            from .depth_template import depth_template,render_depth_template
            result=depth_template(read_json(args.manifest))
            print(json.dumps(result,indent=2)if args.json else render_depth_template(result))
            return 0
        if args.command == "check-case-depths":
            from .case_depths import check_case_depths,render_case_depths
            manifest=read_json(args.manifest)
            if args.plan:
                if args.case is not None or args.max_states is not None:raise ValueError('choose captured plan or manual cases/state budget, not both')
                from .depth_template import consume_depth_plan
                args.case,args.depth,args.max_states=consume_depth_plan(manifest,read_json(args.plan))
            result=check_case_depths(manifest,args.depth,max_states=args.max_states if args.max_states is not None else 5000,selected_ids=args.case)
            print(render_case_depths(result)if args.html else json.dumps(result,indent=2))
            return 2 if result['any_incomplete']else 1 if result['any_unexpected']else 0
        if args.command == "inspect-case-binding":
            from .case_binding import inspect_case_binding,render_case_binding
            result=inspect_case_binding(read_json(args.manifest),read_json(args.report),args.case)
            print(render_case_binding(result)if args.html else json.dumps(result,indent=2))
            return 0 if result['matches_declarations']else 1
        if args.command == "compare-case-depths":
            from .depth_comparison import compare_depth_results,render_depth_comparison
            result=compare_depth_results(read_json(args.before),read_json(args.after))
            print(render_depth_comparison(result)if args.html else json.dumps(result,indent=2))
            return 0
        if args.command == "compare-case-results":
            from .case_comparison import compare_case_results
            result = compare_case_results(read_json(args.before),read_json(args.after),include_coverage=args.include_coverage)
            if args.html:
                from .case_comparison_view import render_case_comparison
                print(render_case_comparison(result))
            else:
                print(json.dumps(result,indent=2,sort_keys=True))
            return 0
        if args.command == "combine-case-manifests":
            from .model_cases import combine_case_manifests,render_case_combination
            left=read_json(args.left);right=read_json(args.right)
            result=combine_case_manifests(left,right)
            print(render_case_combination(result,len(left['cases'])+len(right['cases']))if args.html else json.dumps(result,indent=2))
            return 0
        if args.command == "compare-case-manifests":
            from .model_cases import compare_case_manifests,render_manifest_comparison
            report=compare_case_manifests(read_json(args.left),read_json(args.right))
            print(render_manifest_comparison(report)if args.html else json.dumps(report,indent=2))
            return 0
        if args.command == "case-picker":
            from .model_cases import validated_cases,render_case_selection
            manifest=read_json(args.input);validated_cases(manifest)
            print(render_case_selection(manifest,len(manifest['cases']),interactive=True))
            return 0
        if args.command == "select-cases":
            from .model_cases import select_cases,render_case_selection
            manifest=read_json(args.input)
            selected=select_cases(manifest,args.case)
            print(render_case_selection(selected,len(manifest['cases']))if args.html else json.dumps(selected,indent=2))
            return 0
        if args.command == "inspect-cases":
            from .model_cases import inspect_cases, render_case_inspection
            report=inspect_cases(read_json(args.input),selected_ids=args.case)
            print(render_case_inspection(report) if args.html else json.dumps(report,indent=2))
            return 0
        if args.command == "case-template":
            from .case_template import case_template, render_case_template
            result=case_template(args.fixture)
            if args.html:
                print(render_case_template(result))
            else:
                print(json.dumps(result,indent=2,sort_keys=True))
            return 0
        if args.command == "check-cases":
            from .model_cases import check_cases, cases_summary
            _validate_outputs(None if args.manifest == "-" else args.manifest, [args.report] if args.report else [], args.force)
            if args.manifest == "-":
                from .scenario import decode_json_input, MAX_INPUT_BYTES
                manifest = decode_json_input(sys.stdin.buffer.read(MAX_INPUT_BYTES+1))
            else:
                manifest = read_json(args.manifest)
            result = check_cases(manifest, max_depth=args.max_depth, max_states=args.max_states, selected_ids=args.case)
            if args.report:
                _write(args.report, result, args.force)
            if args.html:
                from .case_run_view import render_case_run
                print(render_case_run(result,max_depth=args.max_depth,max_states=args.max_states))
            else:
                print(json.dumps(cases_summary(result) if args.summary else result, indent=2, sort_keys=True))
            return {"passed":0,"unexpected":1,"incomplete":3}[result["status"]]
        if args.command == "check-many":
            from .model_batch import check_many
            for source in args.scenarios:
                _validate_outputs(source, [args.report] if args.report else [], args.force)
            scenarios = [read_json(path) for path in args.scenarios]
            result = check_many(scenarios, max_depth=args.max_depth, max_states=args.max_states)
            if args.report:
                _write(args.report, result, args.force)
            if args.html:
                from .bounded_search_view import render_search
                print(render_search(result,"batch"))
            else:
                print(json.dumps(result, indent=2, sort_keys=True))
            return 3 if result["any_incomplete"] else int(result["any_failure"])
        if args.command == "suite":
            if args.html and (args.summary or args.json):
                raise ValueError("choose HTML or native JSON/summary suite output")
            _validate_outputs(None, [args.report] if args.report else [], args.force)
            result = run_suite(args.fixture, max_depth=args.max_depth,
                               max_states=args.max_states, max_schedules=args.max_schedules)
            if args.report:
                _write(args.report, result, args.force)
            if args.html:
                from .suite_view import render_suite
                print(render_suite(result))
            elif args.summary:
                from .suite import suite_summary
                print(json.dumps(suite_summary(result), indent=2, sort_keys=True))
            elif args.json:
                print(json.dumps(result, indent=2, sort_keys=True))
            else:
                print(f"Bundled regression suite: {result['status']}")
                for case in result["cases"]:
                    print(f"  {case['fixture']:24} {case['verdict']:16} "
                          f"expected={case['expected_status']} observed={case['report']['status']}")
                    if case["verdict"] != "passed":
                        print(f"    {case['reason']}")
                summary = result["summary"]
                print(f"{summary['passed']}/{summary['cases']} passed; "
                      f"{summary['schedules_checked']} prefixes, {summary['event_steps_executed']} scheduled steps.")
                print(result["scope"])
            return SUITE_EXIT_CODES[result["status"]]
        if args.command == "check":
            _validate_outputs(args.scenario, [path for path in (args.report, args.witness) if path], args.force)
            scenario = validate_scenario(read_json(args.scenario))
            def execute():
                return run_check(scenario, fixture=args.fixture, max_depth=args.max_depth,
                                 max_states=args.max_states, max_schedules=args.max_schedules)
            if args.profile:
                from .profiling import profile_check
                report = profile_check(execute)
            else:
                report = execute()
            witness_allowed = (report["status"] == "merge_interaction_found"
                               and report["candidate"] is not None
                               and (not args.fixture or report["fixture"]["status"] == "agreement"))
            if args.witness and not witness_allowed and Path(args.witness).exists():
                raise ValueError("no verified candidate available; refusing to leave an existing witness that describes an older run")
            witness = make_witness(scenario, report) if args.witness and witness_allowed else None
            if args.report:
                _write(args.report, report, args.force)
            if args.witness and witness_allowed:
                _write(args.witness, witness, args.force,
                       compact=True, max_bytes=MAX_WITNESS_BYTES)
            if args.json:
                print(json.dumps(report, indent=2, sort_keys=True))
            else:
                _show_report(report)
                if args.profile:
                    print(json.dumps(report["measurements"], sort_keys=True))
                if args.witness and not witness_allowed:
                    print("No witness written: no verified candidate is available within the requested scope.")
                elif args.witness:
                    print(f"Witness written: {args.witness}")
                    if args.fixture:
                        print(f"Replay with --fixture {args.fixture} to verify pinned sources and run the handlers.")
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
            if args.require_pin and provenance != "verified":
                raise ValueError("source-pinned witness required by --require-pin")
            result = replay_fixture(witness["scenario"], witness["events"], args.fixture)
            result["source_verification"] = provenance
            if args.summary:
                print(json.dumps(_replay_summary(witness, result, fixture=True), indent=2, sort_keys=True))
            elif args.json:
                if args.trace_limit is not None:
                    from .trace_page import trace_page
                    result = trace_page(witness, result, start=args.from_step, limit=args.trace_limit)
                print(json.dumps(result, indent=2, sort_keys=True))
            else:
                print("Fixture source identity: " + provenance)
                _show_fixture(result)
            return 4 if not result["agreement"] else int(any(
                not outcome["passed"] for outcome in result["observed_outcomes"].values()))
        result["execution_scope"] = "model_only"
        if "fixture" in witness:
            result["source_verification"] = "not_checked"
        if args.summary:
            print(json.dumps(_replay_summary(witness, result), indent=2, sort_keys=True))
        elif args.json:
            if args.trace_limit is not None:
                from .trace_page import trace_page
                result = trace_page(witness, result, start=args.from_step, limit=args.trace_limit)
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
        print(_terminal_text(f"interlock: {exc}"), file=sys.stderr)
        return 2
