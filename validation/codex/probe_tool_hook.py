"""无付费调用地验收已安装 Codex 的结构化工具证据适配。"""
from __future__ import annotations

from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Thread
import runpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from refractrouter.model_gateway import ModelGateway, create_server
from refractrouter.openai_compatible import ChatResponse
configuration = runpy.run_path(str(Path(__file__).resolve().parents[2] /
                                    'tests/test_planning_routing.py'))['configuration']
catalog = runpy.run_path(str(Path(__file__).with_name('model_catalog.py')))['catalog']
from validation.codex.run_with_evidence import run as run_codex


class Caller:
    def __init__(self):
        self.actions = []

    def __call__(self, action, options):
        self.actions.append(deepcopy(action))
        if len(self.actions) <= 2:
            tools = action['tools']
            shell = next((tool for tool in tools if 'cmd' in
                tool.get('parameters', {}).get('properties', {})), None)
            if shell is None:
                raise ValueError('Codex 未提供可用 shell 工具')
            call = {'id': 'call_codex_hook_probe_' + str(len(self.actions)), 'type': 'function',
                    'function': {'name': shell['name'], 'arguments':
                                 json.dumps({'cmd':'false',
                                             'max_output_tokens':200})}}
            return ChatResponse('', 20, 10, 0, 0, 5, 1, 'tool_calls', 'fixture',
                                tool_calls=(call,))
        return ChatResponse('CODEX_HOOK_DONE', 20, 10, 0, 0, 5, 1, 'stop', 'fixture')


def probe():
    with TemporaryDirectory(prefix='refract-codex-hook-') as directory:
        folder = Path(directory)
        caller = Caller()
        planning = configuration('stage')
        planning['maxProductionCost'] = 0
        for model in planning['models']:
            model['contextWindow'] = 1_000_000
            model['maxOutputTokens'] = 8192
        gateway = ModelGateway({'planningRouting':planning}, folder, caller)
        server = create_server(gateway, port=0)
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = f'http://127.0.0.1:{server.server_port}/v1'
        try:
            source = json.loads((Path.home()/'.codex/models_cache.json').read_text())
            models = catalog(source, 'gpt-5.5', gateway.models())
            catalog_file = folder/'models.json'
            catalog_file.write_text(json.dumps(models, ensure_ascii=False))
            (folder/'config.toml').write_text(
                'model_provider="refract"\nweb_search="disabled"\n'
                '[model_providers.refract]\nname="Refract"\nbase_url=' + json.dumps(base) +
                '\nenv_key="REFRACT_FAKE_KEY"\nwire_api="responses"\n'
                'request_max_retries=0\nstream_max_retries=0\n')
            previous = {key:os.environ.get(key) for key in ('REFRACT_FAKE_KEY','CODEX_HOME')}
            os.environ.update(REFRACT_FAKE_KEY='fixture', CODEX_HOME=str(folder))
            command = ['--ignore-rules',
                '--skip-git-repo-check', '--ephemeral', '--sandbox', 'read-only',
                '--dangerously-bypass-hook-trust', '-C', str(folder),
                '-c', 'model_catalog_json=' + json.dumps(str(catalog_file)),
                '-m', 'refract/stage',
                '执行提供的 shell 工具一次，再回答 CODEX_HOOK_DONE。']
            output = io.StringIO()
            diagnostics = {}
            try:
                with redirect_stdout(output):
                    code = run_codex(base, command, diagnostics=diagnostics,
                        hook_command=f'{sys.executable} -m refractrouter.client_tool_evidence')
            finally:
                for key, value in previous.items():
                    if value is None: os.environ.pop(key, None)
                    else: os.environ[key] = value
            events = [json.loads(line) for line in output.getvalue().splitlines()
                      if line.startswith('{')]
            result = {'codexExit':code, 'routerCalls':len(caller.actions),
                      'facts':[fact['status'] for fact in
                               gateway.state.get('hostEvidenceInbox', {}).values()],
                      'models':[action['model']['id'] for action in caller.actions],
                      'reasons':[row.get('reason') for run in gateway.runtime.runs.values()
                                 for row in run.get('decisions', [])],
                      'adapter':diagnostics,
                      'toolItems':[event.get('item') for event in events
                                   if event.get('type') == 'item.completed' and
                                   event.get('item', {}).get('type') == 'command_execution'],
                      'errors':[event.get('message') for event in events if event.get('type') == 'error'],
                      'lastEventTypes':[event.get('type') for event in events[-5:]]}
            print(json.dumps(result, ensure_ascii=False))
            return 0 if code == 0 and result['facts'] == ['failed','failed'] and \
                result['models'] == ['small','small','large'] and \
                'repeated-failure' in result['reasons'] else 1
        finally:
            server.shutdown(); server.server_close(); gateway.close()


if __name__ == '__main__':
    raise SystemExit(probe())
