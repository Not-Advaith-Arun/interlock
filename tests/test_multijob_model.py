import copy
import itertools
from pathlib import Path
import unittest

from interlock.engine import make_witness, replay, replay_witness, search
from interlock.multijob import MultiJobModel
from interlock.scenario import read_json, validate_scenario

ROOT = Path(__file__).resolve().parents[1]


def scenario(safe=False):
    return read_json(ROOT / 'examples' / ('multi_job_safe.json' if safe else 'multi_job_conflict.json'))


class MultiJobModelTests(unittest.TestCase):
    def test_shortest_interaction_requires_two_jobs_and_wrong_ack(self):
        data = scenario()
        report = search(data, max_depth=24)
        self.assertEqual(report['status'], 'merge_interaction_found')
        self.assertEqual(report['coverage']['termination_reason'], 'state_space_exhausted')
        self.assertEqual(report['candidate']['events'], ['submit:a', 'submit:b', 'deliver:b', 'acknowledge:b'])
        for version in ('base', 'left', 'right'):
            self.assertTrue(report['versions'][version]['passed_explored_states'])
        merged = report['candidate']['outcomes']['merged']
        self.assertEqual(merged['state']['completed'], ['a'])
        self.assertEqual(merged['state']['effects'], ['b'])
        self.assertEqual(merged['violations'], ['acknowledgement_matches_completed_job',
                                               'completion_requires_matching_effect'])
        self.assertTrue(replay_witness(make_witness(data, report))['interaction_reproduced'])

    def test_independent_shorter_word_enumeration(self):
        events = ['submit:a', 'submit:b', 'deliver:a', 'deliver:b', 'acknowledge:a', 'acknowledge:b']
        for length in range(4):
            for word in itertools.product(events, repeat=length):
                try:
                    actual = replay(scenario(), word)
                except ValueError:
                    continue
                self.assertFalse(actual['interaction_reproduced'], word)

    def test_wrong_ack_detected_even_when_both_effects_exist(self):
        events = ['submit:a', 'submit:b', 'deliver:a', 'deliver:b', 'acknowledge:b']
        merged = replay(scenario(), events)['outcomes']['merged']
        self.assertEqual(merged['state']['effects'], ['a', 'b'])
        self.assertEqual(merged['violations'], ['acknowledgement_matches_completed_job'])

    def test_later_delivery_cannot_erase_earlier_missing_effect_violation(self):
        events = ['submit:a', 'submit:b', 'deliver:b', 'acknowledge:b', 'deliver:a']
        merged = replay(scenario(), events)['outcomes']['merged']
        self.assertIn('completion_requires_matching_effect', merged['violations'])
        self.assertEqual(merged['state']['effects'], ['b', 'a'])

    def test_correlated_control_accepts_both_delivery_and_ack_reordering(self):
        report = search(scenario(True), max_depth=24)
        self.assertEqual(report['status'], 'no_interaction_within_bound')
        self.assertEqual(report['coverage']['termination_reason'], 'state_space_exhausted')
        for events in (['submit:a', 'submit:b', 'deliver:b', 'acknowledge:b'],
                       ['submit:a', 'submit:b', 'deliver:a', 'deliver:b', 'acknowledge:b']):
            result = replay(scenario(True), events)
            self.assertTrue(all(o['passed'] for o in result['outcomes'].values()))
            self.assertEqual(result['outcomes']['merged']['state']['completed'], ['b'])

    def test_capacity_and_message_identity_control_enabled_events(self):
        model = MultiJobModel()
        config = {'max_in_flight': 1, 'correlate_ack': False}
        state = model.initial(config)
        self.assertEqual(model.enabled(state, config), ('submit:a',))
        state = model.step(state, 'submit:a', config)
        self.assertEqual(model.enabled(state, config), ('deliver:a',))
        state = model.step(state, 'deliver:a', config)
        self.assertEqual(model.enabled(state, config), ('acknowledge:a',))
        state = model.step(state, 'acknowledge:a', config)
        self.assertEqual(model.enabled(state, config), ('submit:b',))
        with self.assertRaisesRegex(ValueError, 'disabled'):
            replay(scenario(), ['submit:a', 'acknowledge:b'])

    def test_inputs_unchanged_and_bounds_still_explicit(self):
        data = scenario()
        original = copy.deepcopy(data)
        self.assertEqual(search(data, max_depth=3)['status'], 'no_interaction_within_bound')
        self.assertEqual(search(data, max_states=2)['status'], 'incomplete')
        self.assertEqual(data, original)

    def test_invalid_configuration_rejected(self):
        for key, value in [('max_in_flight', True), ('max_in_flight', 0), ('max_in_flight', 3),
                           ('correlate_ack', 1), ('correlate_ack', None)]:
            data = scenario()
            data['versions']['left'][key] = value
            with self.assertRaises(ValueError):
                validate_scenario(data)
        data = scenario()
        data['versions']['base']['jobs'] = ['custom']
        with self.assertRaises(ValueError):
            validate_scenario(data)


if __name__ == '__main__':
    unittest.main()
