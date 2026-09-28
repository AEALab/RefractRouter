"""用模拟模型验收 Hermes 终端事实、两次失败及 Stage 换模。"""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
from threading import Thread

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
sys.path.insert(0, str(root/'src'))
from refractrouter.model_gateway import ModelGateway, create_server
from refractrouter.openai_compatible import ChatResponse


def configuration():
    return {'schemaVersion':'refractagent-planning-v1', 'enabled':True,
        'defaultStrategy':'stage', 'maxProductionCost':0, 'timeoutMs':300000,
        'models':[{'id':name, 'provider':'fake', 'model':name,
                   'contextWindow':200000, 'maxOutputTokens':8192,
                   'inputPer1k':.001, 'outputPer1k':.002,
                   'deployment':'local', 'reasoningEffort':'low'}
                  for name in ('small','large','judge')],
        'roles':{'efficient':'small','capable':'large',
                 'classifier':'judge','advisor':'judge'}}


class Caller:
    def __init__(self):
        self.actions = []

    def __call__(self, action, options):
        self.actions.append(deepcopy(action))
        if len(self.actions) <= 2:
            tool = next((row for row in action['tools'] if row['name'] == 'terminal'), None)
            if tool is None:
                raise ValueError('Hermes 未提供 terminal 工具')
            call = {'id':'call_hermes_evidence_' + str(len(self.actions)), 'type':'function',
                    'function':{'name':'terminal', 'arguments':'{"command":"false"}'}}
            return ChatResponse('', 20, 10, 0, 0, 5, 1, 'tool_calls', 'fixture',
                                tool_calls=(call,))
        return ChatResponse('HERMES_EVIDENCE_DONE', 20, 10, 0, 0, 5, 1, 'stop', 'fixture')


def main():
    hermes_root = Path.home()/'.hermes/hermes-agent'
    if not hermes_root.is_dir():
        raise ValueError('未找到已安装的 Hermes 源码')
    sys.path.insert(0, str(hermes_root))
    with TemporaryDirectory(prefix='refract-hermes-evidence-') as directory:
        folder = Path(directory)
        planning = configuration()
        caller = Caller()
        gateway = ModelGateway({'planningRouting':planning}, folder, caller)
        server = create_server(gateway, port=0)
        worker = Thread(target=server.serve_forever, daemon=True); worker.start()
        original = {key:os.environ.get(key) for key in
                    ('REFRACTROUTER_URL','HERMES_DISABLE_LAZY_INSTALLS')}
        os.environ['HERMES_HOME'] = str(folder/'home')
        os.environ['REFRACTROUTER_URL'] = f'http://127.0.0.1:{server.server_port}/v1'
        os.environ['HERMES_DISABLE_LAZY_INSTALLS'] = '1'
        (folder/'home').mkdir()
        try:
            plugin_path = Path(__file__).with_name('refract-tool-evidence')/'__init__.py'
            shutil.copytree(plugin_path.parent, folder/'home/plugins/refract-tool-evidence')
            (folder/'home/config.yaml').write_text(
                'plugins:\n  enabled:\n    - refract-tool-evidence\n')
            from run_agent import AIAgent
            agent = AIAgent(model='refract/stage',
                base_url=f'http://127.0.0.1:{server.server_port}/v1',
                api_key='local-router-test', provider='custom', api_mode='chat_completions',
                enabled_toolsets=['terminal'], reasoning_config={'effort':'low'},
                max_iterations=5, max_tokens=256, quiet_mode=True, skip_memory=True,
                skip_background_review=True, skip_context_files=True,
                load_soul_identity=False, save_trajectories=False, run_budget_seconds=60)
            agent._auto_recovery_cycles=0
            agent._fallback_chain=[]
            agent._fallback_model=None
            agent.client=agent.client.with_options(max_retries=0)
            result=agent.run_conversation('按模型指示执行 terminal 工具。')
            facts = [fact['status'] for fact in
                     gateway.state.get('hostEvidenceInbox', {}).values()]
            models = [action['model']['id'] for action in caller.actions]
            report = {'success':'HERMES_EVIDENCE_DONE' in str(result.get('final_response','')),
                      'facts':facts, 'models':models, 'apiCalls':result.get('api_calls'),
                      'reasons':[row.get('reason') for run in gateway.runtime.runs.values()
                                 for row in run.get('decisions', [])]}
            print(json.dumps(report, ensure_ascii=False))
            return 0 if report['success'] and facts == ['failed','failed'] and \
                models == ['small','small','large'] and \
                'repeated-failure' in report['reasons'] else 1
        finally:
            for key, value in original.items():
                if value is None: os.environ.pop(key, None)
                else: os.environ[key] = value
            server.shutdown();server.server_close();gateway.close()


if __name__ == '__main__':
    raise SystemExit(main())
