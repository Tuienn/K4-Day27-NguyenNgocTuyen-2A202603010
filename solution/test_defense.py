"""Synthetic regression tests; no encrypted streams or hidden harness imports.

Run: python3 -m unittest discover -s solution -p 'test_*.py' -v
"""
import copy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('api', ROOT / 'harness/child_env/api.py')
api = importlib.util.module_from_spec(spec)
sys.modules['api'] = api
spec.loader.exec_module(api)
import defense


class DefenseTests(unittest.TestCase):
    def setUp(self):
        self.ctx = SimpleNamespace(
            baseline=json.loads((ROOT / 'data/baselines.json').read_text()),
            tools=Mock(), state={},
        )
        self.payload = dict(batch_id='batch', contract_id='contract',
                            checkpoint_batch_id='checkpoint', run_id='run',
                            feature_view='features', corpus='docs', chunk_batch_id='chunks')
        b = self.ctx.baseline
        self.profile = dict(row_count=(b['row_count_min'] + b['row_count_max']) / 2,
                            mean_amount=(b['mean_amount_min'] + b['mean_amount_max']) / 2,
                            null_rate={'customer_id': .002}, staleness_min=2.)

    def check(self, handler, tool, result, expected, pillar, payload=None):
        self.ctx.tools.reset_mock()
        getattr(self.ctx.tools, tool).return_value = result
        verdict = handler(payload or self.payload, self.ctx)
        self.assertEqual(verdict.alert, expected)
        self.assertEqual(verdict.pillar, pillar)
        self.assertEqual(len(self.ctx.tools.mock_calls), 1, 'one RPC per event')
        return verdict

    def test_registration(self):
        ctx = SimpleNamespace(on=Mock())
        defense.register(ctx)
        self.assertEqual({call.args[0] for call in ctx.on.call_args_list}, {
            'data_batch', 'contract_checkpoint', 'lineage_run',
            'feature_materialization', 'embedding_batch'})

    def test_batch_individual_faults_and_clean(self):
        self.check(defense.check_data_batch, 'batch_profile', self.profile, False, 'checks')
        for change in ({'row_count': 100}, {'row_count': 900},
                       {'mean_amount': 20}, {'mean_amount': 150},
                       {'null_rate': {'customer_id': .1}}, {'staleness_min': 20}):
            with self.subTest(change=change):
                self.check(defense.check_data_batch, 'batch_profile',
                           dict(self.profile, **change), True, 'checks')

    def test_joint_deviation_inside_individual_limits(self):
        b = self.ctx.baseline
        profile = copy.deepcopy(self.profile)
        profile.update(row_count=b['row_count_max'] - .1,
                       mean_amount=b['mean_amount_max'] - .1)
        self.check(defense.check_data_batch, 'batch_profile', profile, True, 'checks')

    def test_contract_schema_type_and_sla(self):
        for violations, delay, expected in [([], 2, False),
                (['type_violation'], 2, True), (['schema_hash_mismatch'], 2, True),
                ([], 20, True)]:
            with self.subTest(violations=violations, delay=delay):
                self.check(defense.check_contract_checkpoint, 'contract_diff',
                           dict(violations=violations, freshness_delay_min=delay),
                           expected, 'contracts')
        self.check(defense.check_contract_checkpoint, 'contract_diff',
                   dict(violations=[], freshness_delay_min=5), True, 'contracts',
                   dict(self.payload, declared_sla={'freshness_min': 4}))

    def test_contract_at_limit_and_optional_sla(self):
        for sla in (None, {}, {'freshness_min': 15}):
            self.check(defense.check_contract_checkpoint, 'contract_diff',
                       dict(violations=[], freshness_delay_min=self.ctx.baseline['freshness_delay_max_min']),
                       False, 'contracts', dict(self.payload, declared_sla=sla))

    def test_lineage_faults_and_clean(self):
        graph = dict(duration_ms=2500, actual_upstream=['raw.orders', 'raw.customers'],
                     actual_downstream_count=2)
        self.check(defense.check_lineage_run, 'lineage_graph_slice', graph, False, 'lineage')
        for change in ({'duration_ms': 9000}, {'actual_downstream_count': 0},
                       {'actual_upstream': ['raw.orders']},
                       {'actual_upstream': ['raw.customers']}):
            with self.subTest(change=change):
                self.check(defense.check_lineage_run, 'lineage_graph_slice',
                           dict(graph, **change), True, 'lineage')

    def test_feature_natural_variation_and_skew(self):
        for shift, expected in ((0, False), (.472, False), (.65, False), (.970, True)):
            with self.subTest(shift=shift):
                self.check(defense.check_feature_materialization, 'feature_drift',
                           {'mean_shift_sigma': shift}, expected, 'ai_infra')

    def test_embedding_drift_staleness_and_boundaries(self):
        for shift, age, expected in ((.038, 40, False), (.040, 45, False),
                                     (.041, 25, True), (.02, 48, True)):
            with self.subTest(shift=shift, age=age):
                self.check(defense.check_embedding_batch, 'embedding_drift',
                           dict(centroid_shift=shift, avg_doc_age_days=age),
                           expected, 'ai_infra')

    def test_tool_errors_are_diagnostic_and_do_not_retry(self):
        for handler, tool, pillar in (
            (defense.check_data_batch, 'batch_profile', 'checks'),
            (defense.check_contract_checkpoint, 'contract_diff', 'contracts'),
            (defense.check_lineage_run, 'lineage_graph_slice', 'lineage'),
            (defense.check_feature_materialization, 'feature_drift', 'ai_infra'),
            (defense.check_embedding_batch, 'embedding_drift', 'ai_infra'),
        ):
            with self.subTest(tool=tool):
                v = self.check(handler, tool, {'error': 'unavailable'}, False, pillar)
                self.assertEqual(v.confidence, 0)
                self.assertIn('unavailable', v.reason)


if __name__ == '__main__':
    unittest.main()
