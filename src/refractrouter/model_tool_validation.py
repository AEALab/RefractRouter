"""标准模型入口的工具要求验收；仅消费宿主事实，不执行或重试工具。"""
from .task_tool_evidence import tool_requirements
from .planning_policy import text_of

VERSION = 'model-tool-validation-v1'
# 接入方的已知命令工具别名；不从参数或 stdout 推断工具执行成功。
COMMAND_TOOLS = {'bash', 'exec_command', 'functions.exec_command'}


def request_requirements(messages, schemas):
    users = [m for m in messages if m.get('role') == 'user'
             and m.get('wireRole') != 'tool' and text_of(m).strip()]
    return tool_requirements(text_of(users[-1]), schemas) if users else {'required': False, 'tools': []}


def validate_requirements(value):
    if (not isinstance(value, dict) or set(value) != {'required', 'tools'}
            or type(value['required']) is not bool or not isinstance(value['tools'], list)
            or any(not isinstance(n, str) or not n or len(n) > 256 for n in value['tools'])):
        raise ValueError('工具要求合同无效')
    return {'required': value['required'], 'tools': sorted(set(value['tools']))}


def _matches(required, actual):
    required, actual = required.casefold(), actual.casefold()
    return required == actual or required in COMMAND_TOOLS and actual in COMMAND_TOOLS


def verify(requirements, events, *, require_confirmed=False):
    observed = [e for e in events if e['status'] in ({'completed', 'failed'} if require_confirmed
                else {'completed', 'failed', 'unclassified'})]
    missing = [n for n in requirements['tools'] if not any(_matches(n, e['tool']) for e in observed)]
    uncertain = any(e['status'] in {'unconfirmed', 'unclassified', 'unclassified-error'} for e in events)
    passed = not requirements['required'] or bool(observed) and not missing and not (require_confirmed and uncertain)
    reason = ('no-explicit-tool-requirement' if not requirements['required'] else
              'host-tool-status-unconfirmed' if require_confirmed and uncertain else
              'required-host-tool-not-observed' if not passed else 'host-tool-receipt-observed')
    return {'schemaVersion': VERSION, 'required': requirements['required'],
            'requiredTools': requirements['tools'], 'passed': bool(passed), 'reason': reason,
            'missingTools': missing, 'records': [{k: e[k] for k in ('callId', 'tool', 'status')} for e in events],
            'requireConfirmed': require_confirmed, 'outcomeConfirmed': bool(observed) and not uncertain,
            'semanticQualityVerified': False}
