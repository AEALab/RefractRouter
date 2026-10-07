"""已安装 Codex 的四条固定接线验收；模拟模型、真实宿主命令、无付费调用。"""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import runpy
import sys
from tempfile import TemporaryDirectory
from threading import Thread

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from refractrouter.model_gateway import ModelGateway, create_server
from refractrouter.openai_compatible import ChatResponse
from validation.codex.run_with_evidence import run as run_codex
from validation.codex.model_catalog import catalog


class Caller:
    def __init__(self, scenario):
        self.scenario, self.actions = scenario, []

    def __call__(self, action, options):
        self.actions.append(deepcopy(action))
        calls = ()
        if self.scenario != 'missing' and len(self.actions) == 1:
            shell = next(t for t in action['tools'] if 'cmd' in t.get('parameters', {}).get('properties', {}))
            command = 'false' if self.scenario == 'failed' else 'printf REFRACT_RECEIPT_OK'
            calls = ({'id': 'call_requirement_' + self.scenario, 'type': 'function',
                'function': {'name': shell['name'], 'arguments': json.dumps({'cmd': command, 'max_output_tokens': 200})}},)
        return ChatResponse('CODEX_REQUIREMENT_DONE' if not calls else '', 20, 10, 0, 0, 5, 1,
                            'tool_calls' if calls else 'stop', 'fixture', tool_calls=calls)


def probe_one(scenario):
    with TemporaryDirectory(prefix='refract-codex-requirement-') as directory:
        folder = Path(directory)
        config = runpy.run_path(str(Path(__file__).resolve().parents[2] /
                                   'tests/test_planning_routing.py'))['configuration']('static')
        config['maxProductionCost'] = 0
        for model in config['models']:
            model['contextWindow'], model['maxOutputTokens'] = 1_000_000, 8192
        caller = Caller(scenario)
        gw = ModelGateway({'planningRouting': config}, folder/'runs', caller)
        server = create_server(gw, port=0)
        Thread(target=server.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{server.server_port}/v1'
        source = json.loads((Path.home()/'.codex/models_cache.json').read_text())
        (folder/'models.json').write_text(json.dumps(catalog(source, 'gpt-5.5', gw.models())))
        (folder/'config.toml').write_text('model_provider="refract"\nweb_search="disabled"\n'
            '[model_providers.refract]\nname="Refract"\nbase_url=' + json.dumps(base) +
            '\nenv_key="REFRACT_FAKE_KEY"\nwire_api="responses"\nrequest_max_retries=0\nstream_max_retries=0\n')
        previous = {k: os.environ.get(k) for k in ('CODEX_HOME', 'REFRACT_FAKE_KEY')}
        os.environ.update(CODEX_HOME=str(folder), REFRACT_FAKE_KEY='fixture')
        args = ['--ignore-rules', '--skip-git-repo-check', '--ephemeral', '--sandbox', 'read-only',
                '--dangerously-bypass-hook-trust', '-C', str(folder), '-c',
                'model_catalog_json=' + json.dumps(str(folder/'models.json')), '-m', 'refract/static',
                '请使用 Bash 工具执行指定命令，再根据真实宿主结果回答。命令非零退出时如实报告，不重试。']
        diagnostics, output = {}, io.StringIO()
        try:
            with redirect_stdout(output):
                code = run_codex(base, args, diagnostics=diagnostics,
                    hook_command=None if scenario == 'plain-unconfirmed' else
                    f'{sys.executable} -m refractrouter.client_tool_evidence')
            runs = list(gw.runtime.runs.values())
            validation = runs[-1]['state'].get('toolValidation', {})
            expected = scenario in {'executed', 'failed'}
            actual = code == 0 and 'CODEX_REQUIREMENT_DONE' in output.getvalue()
            return {'scenario': scenario, 'passed': actual == expected and bool(validation.get('passed')) == expected,
                    'codexExit': code, 'released': actual, 'paidCalls': 0,
                    'modelCalls': len(caller.actions), 'status': runs[-1]['status'],
                    'validation': validation, 'resolvedIds': diagnostics.get('resolvedIds', []),
                    'hostCommands': diagnostics.get('completed', [])}
        finally:
            for key, value in previous.items():
                if value is None: os.environ.pop(key, None)
                else: os.environ[key] = value
            server.shutdown(); server.server_close(); gw.close()


if __name__ == '__main__':
    rows = [probe_one(s) for s in ('executed', 'failed', 'missing', 'plain-unconfirmed')]
    print(json.dumps({'codexCases': rows, 'paidCalls': 0}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if all(r['passed'] for r in rows) else 1)
