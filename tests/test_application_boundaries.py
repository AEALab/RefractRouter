"""Application regressions for verdict, billing and residual recovery state."""
from copy import deepcopy
from dataclasses import replace
import json

import pytest

from refractrouter.task_plan import validate_plan
from refractrouter.task_scheduling import ExecutionPolicy, estimate_schedule
from tests.test_node_recovery import BrokenNode
from tests.test_profile_strata import corpus, build
from tests.test_task_decomposition import example
from tests.test_text_tasks import Client, MANIFEST, PROFILE, REQUEST, live


class OmittedRequirementJudge(Client):
    def complete(self, model, messages, *, json_mode=False):
        response = super().complete(model, messages, json_mode=json_mode)
        if model.role == 'judge':
            verdict = json.loads(response.content)
            verdict.update(score=55, passed=False, rationale='原任务要求给出来源，但最终答案未给出。')
            return replace(response, content=json.dumps(verdict))
        return response


def test_overall_failure_is_retained_when_listed_criteria_all_pass():
    result = live(OmittedRequirementJudge(), task='请简短回答并给出来源。',
                  plan=example('single-answer'))
    assert result['status'] == 'quality-failed', result['issues']
    assert result['evaluation']['score'] == 55
    assert all(row['passed'] for row in result['evaluation']['criteria'])
    assert result['final_output'] and result['charged']['evaluation'] > 0


def test_overall_success_still_requires_each_listed_criterion():
    class Contradictory(Client):
        def complete(self, model, messages, *, json_mode=False):
            response = super().complete(model, messages, json_mode=json_mode)
            if model.role == 'judge':
                verdict = json.loads(response.content)
                verdict['criteria'][0]['passed'] = False
                return replace(response, content=json.dumps(verdict))
            return response
    result = live(Contradictory(), plan=example('single-answer'))
    assert result['status'] == 'failed' and result['evaluation'] is None
    assert result['issues'] == ['inconsistent final judge verdict']
    assert result['final_output']


@pytest.mark.parametrize('field', ['input_tokens', 'output_tokens', 'all'])
@pytest.mark.parametrize('kind', ['empirical', 'synthetic'])
def test_nonempty_profile_observations_require_positive_input_and_output_usage(field, kind):
    raw = corpus()
    raw['kind'] = kind
    for row in raw['observations']:
        if field == 'all':
            row['usage'] = dict.fromkeys(row['usage'], 0)
        else:
            row['usage'][field] = 0
    with pytest.raises(ValueError, match='missing billed usage'):
        build(raw)


def test_residual_schedule_keeps_provider_spacing_and_inflight_work():
    plan = validate_plan(example())
    providers = {n.node_id: 'shared' for n in plan.nodes}
    forecast = estimate_schedule(plan, {'cost': 1, 'risk': 40, 'answer': 1}, providers,
        ExecutionPolicy(2, provider_min_interval_ms={'shared': 100}),
        active={'risk'}, last_start={'shared': -20})
    assert forecast['nodes']['risk']['end_ms'] == 40
    assert forecast['nodes']['cost']['start_ms'] == 80
    assert forecast['nodes']['answer']['start_ms'] == 180
    assert forecast['makespan_ms'] == 181
    # Completed work must not consume a new start interval or a worker slot.
    forecast = estimate_schedule(plan, {'cost': 0, 'risk': 1, 'answer': 1}, providers,
        ExecutionPolicy(2, provider_min_interval_ms={'shared': 100}),
        completed={'cost'}, last_start={'shared': -100})
    assert forecast['nodes']['risk']['start_ms'] == 0
    assert forecast['makespan_ms'] == 101


def test_recovery_declines_replacement_that_cannot_start_before_deadline():
    from refractrouter.task_runtime import run_task
    profile = deepcopy(PROFILE)
    profile['kind'] = 'empirical'
    for row in profile['candidates']:
        row['latency_ms'] = 1
    client = BrokenNode(kind='truncated', nid='answer')
    result = run_task({**REQUEST, 'method': 'A', 'weights': None,
                      'plan': example('single-answer'), 'latencyMaxMs': 100,
                      'maxNodeFallbacks': 1,
                      'providerMinIntervalMs': {MANIFEST.candidates[0].provider: 1000}},
                     MANIFEST, profile, client=client, production_limit=100, evaluation_limit=100)
    assert len(client.seen) == 1
    assert not result['recovery']['events']
    assert result['nodes'][0]['recovery_status'] == 'no-feasible-replacement'
    assert len(result['calls']) == 1 and result['calls'][0]['status'] == 'billed'
