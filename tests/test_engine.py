import copy
import itertools
import json
from pathlib import Path
import tempfile
import unittest

from interlock.engine import make_witness, replay, replay_witness, search
from interlock.scenario import fingerprint, read_json, validate_scenario

ROOT = Path(__file__).resolve().parents[1]


def scenario(name="retry_conflict"):
    return read_json(ROOT / "examples" / f"{name}.json")


class SearchTests(unittest.TestCase):
    def test_finds_interaction_with_individually_safe_versions(self):
        result = search(scenario())
        self.assertEqual(result["status"], "merge_interaction_found")
        self.assertTrue(result["coverage"]["complete_up_to_depth"])
        for version in ("base", "left", "right"):
            self.assertTrue(result["versions"][version]["passed_explored_states"])
        self.assertFalse(result["versions"]["merged"]["passed_explored_states"])
        self.assertEqual(result["candidate"]["events"], ["submit", "deliver", "timeout", "deliver"])
        self.assertEqual(result["candidate"]["outcomes"]["merged"]["state"]["effects"], 2)

    def test_shortest_witness_independent_bruteforce(self):
        # Separate exhaustive word generation checks the BFS minimality claim.
        data = scenario()
        alphabet = ("submit", "deliver", "timeout", "acknowledge", "drop_ack")
        for length in range(4):
            for events in itertools.product(alphabet, repeat=length):
                try:
                    result = replay(data, events)
                except ValueError:
                    continue
                self.assertFalse(result["interaction_reproduced"], events)

    def test_deleting_any_witness_event_destroys_interaction(self):
        data = scenario()
        events = search(data)["candidate"]["events"]
        for index in range(len(events)):
            try:
                result = replay(data, events[:index] + events[index + 1:])
            except ValueError:
                continue
            self.assertFalse(result["interaction_reproduced"])

    def test_fix_prevents_false_positive(self):
        result = search(scenario("retry_safe"), max_depth=12)
        self.assertEqual(result["status"], "no_interaction_within_bound")
        self.assertIsNone(result["candidate"])

    def test_shallow_bound_reports_scope(self):
        result = search(scenario(), max_depth=3)
        self.assertEqual(result["status"], "no_interaction_within_bound")
        self.assertEqual(result["coverage"]["depth_reached"], 3)
        self.assertEqual(search(scenario(), max_depth=4)["status"], "merge_interaction_found")

    def test_zero_depth_checks_initial_state(self):
        result = search(scenario(), max_depth=0)
        self.assertEqual(result["coverage"]["states_explored"], 1)
        self.assertEqual(result["coverage"]["transitions_explored"], 0)

    def test_budget_exhaustion_cannot_claim_clean(self):
        result = search(scenario(), max_states=2)
        self.assertEqual(result["status"], "incomplete")
        self.assertFalse(result["coverage"]["complete_up_to_depth"])
        self.assertLessEqual(result["coverage"]["states_discovered"], 2)

    def test_baseline_failure_is_not_merge_interaction(self):
        self.assertEqual(search(scenario("baseline_failure"))["status"], "baseline_failure")

    def test_branch_failure_is_not_merge_interaction(self):
        self.assertEqual(search(scenario("branch_failure"))["status"], "branch_failure")

    def test_deterministic_and_input_not_mutated(self):
        data = scenario()
        before = copy.deepcopy(data)
        self.assertEqual(search(data), search(data))
        self.assertEqual(data, before)

    def test_safe_ack_prevents_retry(self):
        result = replay(scenario(), ["submit", "deliver", "acknowledge"])
        self.assertFalse(result["interaction_reproduced"])
        with self.assertRaisesRegex(ValueError, "disabled in all versions"):
            replay(scenario(), ["submit", "deliver", "acknowledge", "timeout"])

    def test_lost_ack_reproduces_interaction(self):
        result = replay(scenario(), ["submit", "deliver", "drop_ack", "timeout", "deliver"])
        self.assertTrue(result["interaction_reproduced"])

    def test_in_flight_retry_is_processed_even_after_ack(self):
        result = replay(scenario(), ["submit", "deliver", "timeout", "acknowledge", "deliver"])
        self.assertTrue(result["interaction_reproduced"])

    def test_stuttering_is_explicit(self):
        result = replay(scenario(), ["submit", "timeout"])
        self.assertEqual(result["trace"][2]["stuttered"], ["base", "right"])

    def test_finite_state_adapter(self):
        result = search(scenario("callback_conflict"))
        self.assertEqual(result["status"], "merge_interaction_found")
        self.assertEqual(result["candidate"]["events"], ["allocate", "cancel", "callback"])

    def test_transient_failure_cannot_be_erased(self):
        data = scenario("callback_conflict")
        data["versions"]["merged"]["states"]["freed_access"]["on"] = {"recover": "done"}
        result = replay(data, ["allocate", "cancel", "callback", "recover"])
        self.assertTrue(result["interaction_reproduced"])
        self.assertEqual(result["outcomes"]["merged"]["state"], {"state": "done"})

    def test_failure_elsewhere_disqualifies_clean_branch_claim(self):
        data = scenario("callback_conflict")
        states = data["versions"]["left"]["states"]
        states["idle"]["on"]["unrelated_regression"] = "freed_access"
        result = search(data)
        self.assertIsNotNone(result["candidate"])
        self.assertEqual(result["status"], "branch_failure")

    def test_witness_roundtrip(self):
        data = scenario()
        witness = make_witness(data, search(data))
        result = replay_witness(json.loads(json.dumps(witness)))
        self.assertTrue(result["interaction_reproduced"])

    def test_changed_scenario_breaks_fingerprint(self):
        data = scenario()
        witness = make_witness(data, search(data))
        witness["scenario"]["versions"]["merged"]["deduplicate"] = True
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            replay_witness(witness)

    def test_fingerprint_order_independent(self):
        data = scenario()
        self.assertEqual(fingerprint(data), fingerprint(dict(reversed(list(data.items())))))

    def test_bounds_validation(self):
        for value in (-1, 65, True, "8"):
            with self.assertRaises(ValueError):
                search(scenario(), max_depth=value)
        for value in (0, 1_000_001, True, "8"):
            with self.assertRaises(ValueError):
                search(scenario(), max_states=value)

    def test_scenario_validation(self):
        for key, value in (("model", "evil:run"), ("model", []), ("name", ""), ("format", "v2")):
            data = scenario()
            data[key] = value
            with self.assertRaises(ValueError):
                validate_scenario(data)
        for value in (-1, 17, True, "1"):
            data = scenario()
            data["versions"]["left"]["retry_limit"] = value
            with self.assertRaises(ValueError):
                validate_scenario(data)

    def test_fsm_validation_rejects_unknown_target(self):
        data = scenario("callback_conflict")
        data["versions"]["base"]["states"]["idle"]["on"]["allocate"] = "missing"
        with self.assertRaisesRegex(ValueError, "unknown destination"):
            validate_scenario(data)

    def test_duplicate_json_fields_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"name":"one","name":"two"}')
            with self.assertRaisesRegex(ValueError, "duplicate JSON field"):
                read_json(path)

    def test_nonstandard_json_constant_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nan.json"
            path.write_text('{"value":NaN}')
            with self.assertRaisesRegex(ValueError, "invalid JSON constant"):
                read_json(path)

    def test_oversized_input_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "large.json"
            path.write_bytes(b" " * 2_000_001)
            with self.assertRaisesRegex(ValueError, "2 MB"):
                read_json(path)


if __name__ == "__main__":
    unittest.main()
