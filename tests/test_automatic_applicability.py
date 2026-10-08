"""有限实验的事实判定和历史额度去重，不调用模型。"""
import json
import pytest

from experiments.run_automatic_applicability import (
    historical_protection, historical_roots, task_check, bounded_complete,
)


def test_private_evidence_cash_remains_protected_across_worktree_and_installation(tmp_path):
    root, deployed = tmp_path/'worktree', tmp_path/'installed'
    call = {'model_id': 'cash', 'dispatch_at': '2026-10-08T00:00:00Z',
            'input_sha256': 'one', 'status': 'billed', 'charged': .2}
    unknown = {**call, 'input_sha256': 'two', 'status': 'unknown-usage', 'charged': .3}
    for base, rows in ((root, [call]), (deployed, [call, unknown])):
        folder = base/'.refractagent/private-audit/batch/task/direct'
        folder.mkdir(parents=True)
        (folder/'manifest.json').write_text(json.dumps({'models': [
            {'model_id': 'cash', 'deployment': 'trusted-cloud', 'billing_mode': 'metered'}]}))
        (folder/'result.json').write_text(json.dumps({'billing_unit': 'CNY', 'calls': rows}))
    protected = historical_protection(historical_roots(root, deployed))
    assert protected['cashProtectedCny'] == .5
    assert protected['unknownCount'] == 1
    assert len(protected['calls']) == 2


def test_finite_runner_records_all_routes_with_local_model_fixtures(tmp_path, monkeypatch):
    """完整调用胶水无网络验证，防止期限／空计划／路径汇总故障进入付费批次。"""
    import io
    import experiments.run_automatic_applicability as runner
    from refractrouter.application_config import compile_configuration
    from tests.test_live_execution import CompactClient, config
    raw = config()
    raw['billingUnit'] = 'CNY'
    for model in raw['models']:
        model['pricing']['unit'] = 'CNY'  # 模拟价格单位，不是美元到人民币换算。
    models = compile_configuration(raw).manifest.models
    catalog = {'routes': [{'provider': m.provider, 'model': m.api_model} for m in models]}
    class Process:
        def __init__(self, *_args, **_kwargs):
            self.stdin = io.StringIO()
            self.stdout = io.StringIO(json.dumps(catalog)+'\n')
        def wait(self, **_kwargs):
            return 0
    class Client(CompactClient):
        def __init__(self, **_kwargs):
            super().__init__()
        def for_task_call(self, _seconds):
            return self
    monkeypatch.setattr(runner.subprocess, 'Popen', Process)
    monkeypatch.setattr(runner, 'OpenAICompatibleClient', Client)
    task = {'id': 'one', 'task': '分别核对第一项事实和第二项风险，汇总建议。',
            'criteria': ['完整回答并解释边界。'], 'expectedAnswers': {'foo': False}}
    protocol = {'tasks': [task], 'maxCallsPerDirect': 2, 'maxCallsPerDag': 8,
        'outputLimitPerCall': 8192, 'inputBoundPerCall': 32768, 'timeoutMs': 300000,
        'plannerTimeoutMs': 90000}
    frozen = {'protocol': protocol, 'order': [{'task': 'one', 'route': r} for r in ('direct', 'dag')],
        'configuration': raw, 'provenance': {}, 'maximumReferenceCny': 1000, 'maximumCashCny': 1000,
        'maximumModelCalls': 10}
    output = tmp_path/'fresh'
    rows = runner.run(frozen, output, ['fixture'], catalog)
    assert len(rows) == 2
    assert [r['modelCalls'] for r in rows] == [2, 5]
    assert json.loads((output/'completion.json').read_text())['complete']
    ledger = json.loads((output/'batch-ledger.json').read_text())
    assert all(r['status']=='billed' for r in ledger['records'])
    assert all(not r['resultPath'].startswith('/') for r in rows)


def test_null_plan_and_unknown_usage_stop_the_whole_batch(tmp_path, monkeypatch):
    import io
    import experiments.run_automatic_applicability as runner
    from refractrouter.application_config import compile_configuration
    from tests.test_live_execution import config
    raw = config()
    raw['billingUnit'] = 'CNY'
    for model in raw['models']:
        model['pricing']['unit'] = 'CNY'
    models = compile_configuration(raw).manifest.models
    catalog = {'routes': [{'provider': m.provider, 'model': m.api_model} for m in models]}
    class Process:
        def __init__(self, *_args, **_kwargs):
            self.stdin=io.StringIO(); self.stdout=io.StringIO(json.dumps(catalog)+'\n')
        def wait(self, **_kwargs):
            return 0
    calls=[]
    class Client:
        max_retries=0
        def __init__(self, **_kwargs):
            pass
        def for_task_call(self, _seconds):
            return self
        def complete(self, model, messages, *, json_mode=False):
            calls.append(model.model_id)
            raise TimeoutError('fixture timeout; no remote traffic')
    monkeypatch.setattr(runner.subprocess,'Popen',Process)
    monkeypatch.setattr(runner,'OpenAICompatibleClient',Client)
    task={'id':'one','task':'分别核对两项材料并汇总建议。','criteria':['完整回答。'],'expectedAnswers':{}}
    frozen={'protocol':{'tasks':[task],'maxCallsPerDirect':2,'maxCallsPerDag':8,'outputLimitPerCall':8192,
        'inputBoundPerCall':32768,'timeoutMs':300000,'plannerTimeoutMs':90000},
        'order':[{'task':'one','route':r} for r in ('dag','direct')], 'configuration':raw,
        'provenance':{},'maximumReferenceCny':1000,'maximumCashCny':1000,'maximumModelCalls':10}
    with pytest.raises(ValueError,match='未确认调用'):
        runner.run(frozen,tmp_path/'fresh',['fixture'],catalog)
    assert len(calls)==1
    completed=json.loads((tmp_path/'fresh/completion.json').read_text())
    assert completed['finished']==1 and not completed['complete']
    ledger=json.loads((tmp_path/'fresh/batch-ledger.json').read_text())
    assert ledger['records'][0]['status']=='unknown-usage'


def test_timeout_uses_client_snapshot_instead_of_unsupported_complete_argument():
    events = []
    class Client:
        def for_task_call(self, seconds):
            events.append(('deadline', seconds))
            return self
        def complete(self, model, messages, *, json_mode=False):
            events.append(('complete', model, messages, json_mode))
            return 'receipt'
    assert bounded_complete(Client(), 'model', [], json_mode=True, timeout_seconds=30) == 'receipt'
    assert events == [('deadline', 30), ('complete', 'model', [], True)]


def test_fact_check_rejects_missing_false_bool_and_unexplained_results():
    task = {'expectedAnswers': {'amount': .12, 'confirmed': False, 'subscriptionCash': None}}
    good = {'answers': {'amount': .120000000001, 'confirmed': False, 'subscriptionCash': None},
            'explanation': '明确区分原生用量、参考估值及现金归属。'}
    assert task_check(json.dumps(good), task)['passed']
    good['answers']['confirmed'] = 0
    assert not task_check(json.dumps(good), task)['passed']
    good['answers']['confirmed'] = False
    del good['answers']['subscriptionCash']
    assert not task_check(json.dumps(good), task)['passed']
    good['answers']['subscriptionCash'] = None
    good['explanation'] = ''
    assert not task_check(json.dumps(good), task)['passed']


def test_history_counts_unknown_and_deduplicates_copies(tmp_path):
    model = {'model_id': 'cash', 'deployment': 'trusted-cloud', 'billing_mode': 'metered'}
    call = {'model_id': 'cash', 'dispatch_at': '2026-10-08T00:00:00Z',
            'input_sha256': 'one', 'status': 'unknown-usage', 'charged': .1}
    def save(name, row, unit='CNY', mode='run', override=None):
        folder = tmp_path/name; folder.mkdir()
        (folder/'manifest.json').write_text(json.dumps({'models': [override or model]}))
        (folder/'result.json').write_text(json.dumps({'mode':mode, 'billing_unit':unit, 'calls':[row]}))
    save('a', call); save('copy', call)
    assert historical_protection([tmp_path])['cashProtectedCny'] == .1
    settled = {**call, 'status':'billed', 'charged':.02}
    save('settled', settled)
    save('old-afp', {**call, 'input_sha256':'afp'}, unit='AFP')
    save('simulation', {**call, 'input_sha256':'sim'}, mode='demo')
    save('subscription', {**call, 'input_sha256':'sub'}, override={**model,'billing_mode':'subscription'})
    result = historical_protection([tmp_path])
    assert result['cashProtectedCny'] == .02
    assert result['unknownCount'] == 0
    save('conflict', {**settled, 'charged':.03})
    with pytest.raises(ValueError, match='费用记录冲突'):
        historical_protection([tmp_path])


@pytest.mark.parametrize('failure_type,confirmed,finishes', [
    ('provider-error', True, 2), ('authentication', True, 1), ('provider-error', False, 1),
])
def test_complete_batch_pipeline_preserves_failure_receipts_and_stop_policy(tmp_path, monkeypatch, failure_type, confirmed, finishes):
    import io
    import experiments.run_automatic_applicability as runner
    from refractrouter.application_config import compile_configuration
    from refractrouter.openai_compatible import ChatResponse, ModelInvocationError
    from tests.test_live_execution import CompactClient, config
    raw = config()
    raw['billingUnit'] = 'CNY'
    for model in raw['models']:
        model['pricing']['unit'] = 'CNY'
    models = compile_configuration(raw).manifest.models
    catalog = {'routes': [{'provider':m.provider,'model':m.api_model} for m in models]}
    class Process:
        def __init__(self, *_args, **_kwargs):
            self.stdin=io.StringIO(); self.stdout=io.StringIO(json.dumps(catalog)+'\n')
        def wait(self, **_kwargs):
            return 0
    calls=[]
    class Client(CompactClient):
        def __init__(self, **_kwargs):
            super().__init__()
        def for_task_call(self, _seconds):
            return self
        def complete(self, model, messages, *, json_mode=False):
            calls.append(model.model_id)
            if len(calls)==1:
                receipt=ChatResponse('partial',100,20,0,0,1,1,'error','failed') if confirmed else None
                raise ModelInvocationError(failure_type,'fixture',1,1,confirmed_response=receipt)
            return super().complete(model,messages,json_mode=json_mode)
    monkeypatch.setattr(runner.subprocess,'Popen',Process)
    monkeypatch.setattr(runner,'OpenAICompatibleClient',Client)
    task={'id':'one','task':'分别核对两项材料并汇总建议。','criteria':['完整回答。'],'expectedAnswers':{}}
    frozen={'protocol':{'tasks':[task],'maxCallsPerDirect':2,'maxCallsPerDag':8,'outputLimitPerCall':8192,
        'inputBoundPerCall':32768,'timeoutMs':300000,'plannerTimeoutMs':90000},
        'order':[{'task':'one','route':r} for r in ('dag','direct')], 'configuration':raw,
        'provenance':{},'maximumReferenceCny':1000,'maximumCashCny':1000,'maximumModelCalls':10}
    output=tmp_path/'fresh'
    if finishes==2:
        rows=runner.run(frozen,output,['fixture'],catalog)
        assert len(rows)==2 and rows[0]['status']!='completed'
        assert rows[1]['modelCalls']==2
    else:
        with pytest.raises(ValueError,match='停止后续调用'):
            runner.run(frozen,output,['fixture'],catalog)
        assert len(calls)==1
    completion=json.loads((output/'completion.json').read_text())
    assert completion['finished']==finishes
    first=json.loads((output/'batch-ledger.json').read_text())['records'][0]
    assert first['status']==('billed' if confirmed else 'unknown-usage')
    assert first['failure']['failure_type']==failure_type


def test_freeze_includes_compiled_bridge_and_changes_when_bridge_changes(tmp_path, monkeypatch):
    import experiments.run_automatic_applicability as runner
    monkeypatch.setattr(runner,'ROOT',tmp_path)
    # 测试哈希合同，不依赖真实安装或访问网络。
    monkeypatch.setattr(runner,'__file__',str(tmp_path/'runner.py'))
    for name in ('HOST','HOST_AUDIT','PROTOCOL'):
        path=tmp_path/name; path.write_text(name); monkeypatch.setattr(runner,name,path)
    plugin=tmp_path/'validation/dsh/plugin'
    (plugin/'dist').mkdir(parents=True); (plugin/'src').mkdir()
    (plugin/'package-lock.json').write_text('{}')
    (tmp_path/'runner.py').write_text('fixture')
    with pytest.raises(ValueError,match='先构建'):
        runner.source_hashes()
    bridge=plugin/'dist/index.js'; bridge.write_text('generated fixture one')
    first=runner.source_hashes()
    assert 'validation/dsh/plugin/dist/index.js' in first
    bridge.write_text('generated fixture two')
    assert runner.source_hashes()!=first


def test_materials_remain_bound_to_original_commit_after_runtime_repairs(monkeypatch):
    from types import SimpleNamespace
    import hashlib
    import experiments.run_automatic_applicability as runner
    calls=[]
    def read(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(stdout=b'original material')
    monkeypatch.setattr(runner.subprocess,'run',read)
    commit='a'*40
    task={'materials':[{'path':'src/example.py','sha256':hashlib.sha256(b'original material').hexdigest()}]}
    runner.validate_materials({'sourceCommit':commit,'tasks':[task,task]})
    assert calls==[['git','show',f'{commit}:src/example.py']]
    with pytest.raises(ValueError,match='摘要不匹配'):
        runner.validate_materials({'sourceCommit':commit,'tasks':[{'materials':[
            {'path':'src/example.py','sha256':'wrong'}]}]})
    with pytest.raises(ValueError,match='完整来源提交'):
        runner.validate_materials({'sourceCommit':'main','tasks':[task]})
