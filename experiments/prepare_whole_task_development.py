"""离线冻结六道封闭开发题；公开输入与隔离评分材料分目录保存。"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import random
import tomllib

from refractrouter.development_evaluation import apply_edits, evaluate, tree_sha


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def scope(text, symbol):
    lines = text.splitlines(keepends=True)
    candidates = []
    def visit(nodes, prefix=''):
        for node in nodes:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = prefix + node.name
                if name == symbol:
                    candidates.append((sum(map(len, lines[:node.lineno-1])), sum(map(len, lines[:node.end_lineno]))))
                visit(node.body, name + '.')
    visit(ast.parse(text).body)
    if len(candidates) != 1:
        raise ValueError('冻结符号须唯一')
    return candidates[0]


def build(source_root, output, finance_path):
    source_root, output = Path(source_root), Path(output)
    if output.exists():
        raise ValueError('必须使用新的证据目录')
    source_raw = (source_root / 'sources.json').read_bytes()
    sources = json.loads(source_raw)['sources']
    finance_raw = Path(finance_path).read_bytes()
    finance = json.loads(finance_raw)
    if (finance['cash_limit_cny'] != '300' or not finance['plan_no_overage_is_user_declared']
            or not finance['all_current_calls_settled'] or finance['unknown_reserves_released']):
        raise ValueError('历史财务承接条件不符')
    output.mkdir(parents=True)
    write(output / 'source-provenance.json', json.loads(source_raw))
    tasks, private = [], {}

    def task(repo, kind, fields, edits=None):
        source = next(s for s in sources if s['repository'] == repo)
        task_id = 'dev-' + repo.split('/')[-1]
        root = output / 'visible' / task_id
        files = {}
        for row in source['files']:
            raw = (source_root / repo.replace('/', '--') / row['path']).read_bytes()
            if digest(raw) != row['sha256']:
                raise ValueError('来源哈希变化')
            target = root / row['path']; target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            files[row['path']] = raw.decode()
        answers, evidence, gold_refs, field_questions = {}, {}, {}, {}
        for key, question, answer, supports in fields(files):
            answers[key] = answer
            field_questions[key] = {'question': question, 'type': type(answer).__name__}
            evidence[key], gold_refs[key] = [], []
            for path, symbol, quote in supports:
                text = files[path]
                start, end = scope(text, symbol) if symbol else (0, len(text))
                alternatives = quote if isinstance(quote, list) else [quote]
                if any(q not in text[start:end] or len(q.encode()) > 4096 for q in alternatives):
                    raise ValueError('冻结证据不可用')
                group = {'path': path, 'start': start, 'end': end,
                    'allOf': [] if isinstance(quote, list) else [quote]}
                if isinstance(quote, list): group['anyOf'] = quote
                evidence[key].append(group)
                gold_refs[key].append({'path': path, 'quote': alternatives[0]})
        replacements = edits(files) if edits else []
        changed = apply_edits(files, replacements)
        criteria = {'taskId': task_id, 'kind': kind, 'fields': field_questions,
            'patchRequirement': PATCH_QUESTIONS.get(repo, '本题只分析，edits 必须为 []。'),
            'contract': CONTRACT}
        oracle = {'criteriaSha256': digest(json.dumps(criteria, ensure_ascii=False, sort_keys=True).encode()),
            'answers': answers, 'evidence': evidence,
            'expectedTrees': {p: tree_sha(changed[p]) for p in files if changed[p] != files[p]},
            'filesSha256': {p: digest(t.encode()) for p, t in files.items()}}
        gold = {'answers': answers, 'evidence': gold_refs, 'edits': replacements}
        if not evaluate(json.dumps(gold), files, oracle)['passed']:
            raise ValueError('离线参考解未满足冻结规则')
        private[task_id] = {'oracle': oracle, 'goldSelfTest': gold}
        host = {'schemaVersion': 'readonly-facts-host-v1', 'root': str(root.resolve()), 'files': oracle['filesSha256']}
        write(output / 'visible' / f'{task_id}-host.json', host)
        tasks.append({'taskId': task_id, 'kind': kind, 'repository': repo, 'sourceCommit': source['commit'],
            'half': len(tasks) % 2, 'criteria': criteria, 'criteriaSha256': oracle['criteriaSha256'],
            'files': source['files'], 'root': f'visible/{task_id}',
            'host': f'visible/{task_id}-host.json',
            'hostSha256': digest((output / 'visible' / f'{task_id}-host.json').read_bytes())})

    task('pallets/click', '确定性提取', click)
    task('tox-dev/platformdirs', '确定性提取', platformdirs)
    task('urllib3/urllib3', '跨文件受控修改', urllib, urllib_edits)
    task('tkem/cachetools', '跨文件受控修改', cachetools, cache_edits)
    task('encode/httpcore', '证据约束分析', httpcore)
    task('agronholm/anyio', '证据约束分析', anyio)
    order = []
    randomizer = random.Random(20261030)
    for row in tasks:
        arms = ['S0', 'W0', 'WF']; randomizer.shuffle(arms)
        order.extend({'taskId': row['taskId'], 'arm': arm} for arm in arms)
    manifest = {'schemaVersion': 'whole-task-development-v1', 'modelCallsAtFreeze': 0,
        'sourcesManifestSha256': digest(source_raw), 'tasks': tasks, 'order': order,
        'seed': 20261030, 'sourceDesign': '真实公开快照上的人工受控题；不是自然缺陷票据或随机总体样本。',
        'oldTaskUse': '旧两题不计新样本，当前六项目与历史开发题项目分离；训练污染未知。',
        'heldout': {'plannedCount': 24, 'perKind': 8, 'materializedCount': 0,
            'status': '仅预留名额；开发筛选有增益后才独立采集，当前无留出结论。'},
        'models': {'S0': 'glm-5.3', 'W0': 'glm-5.3-flash', 'WF': 'glm-5.3-flash'},
        'output': {'wireAnswerTokens': 131072, 'contextWindow': 1024000,
            'costContextEnvelopeTokens': 1048576, 'thinking': {'type': 'enabled'}, 'reasoningEffort': 'low'},
        'limits': {'maxCalls': 36, 'maxWFCallsPerTask': 4, 'maxToolQueriesPerTask': 8,
            'maxInputBytes': 512000, 'httpAutomaticRetries': 0, 'perCallTimeoutSeconds': 600,
            'batchTimeboxSeconds': 10800, 'maxDevelopmentRevisions': 1},
        'billing': {'unit': 'standardAFP', 'strongPer1kInputAndOutput': .45,
            'weakPer1kInputAndOutput': .05, 'maxStandardAFP': 4404.0192,
            'incrementalCashConditionalOnPlanNoOverageCNY': 0, 'actualProviderDebitVerified': False},
        'funding': {'sourcePath': str(Path(finance_path).resolve()), 'sourceSha256': digest(finance_raw),
            'cashLimitCNY': finance['cash_limit_cny'], 'priorProtectedCashCNY': finance['cumulative_cash_protected_cny'],
            'priorUnknownCashCNYAlreadyIncluded': finance['historical_unknown_cash_retained_cny'],
            'priorKnownStandardAFP': finance['cumulative_known_standard_afp_lower'],
            'priorUnknownStandardAFP': finance['cumulative_unknown_reserved_standard_afp'],
            'sourceTimeUTC': finance['time_utc'], 'laterResearchCallsBeforeThisBatch': 0,
            'scope': '本研究已核对账本；不是整个账户余额，未知预留不释放。'},
        'stopping': '认证/未知用量/材料或证据漂移停止整批；已知题目失败计失败且保留费用。完成六题后，有明确质量回退即停止配置扩量；无工具增益或精度不足均保持默认，不自动追样本。',
        'releaseAllowed': False, 'productPathChanged': False}
    write(output / 'manifest.json', manifest)
    write(output / 'isolated-evaluation' / 'oracles.json', private)
    return manifest


CONTRACT = ('只输出一个 JSON 对象，恰含 answers、evidence、edits。answers 含本题列出的全部字段，'
    '值使用标注的原生类型，不写解释文字。evidence 使用同名字段，每个值是1至8条 '
    '{"path":"精确相对路径","quote":"连续、逐字符原文"}；每条引用须支持该字段，不能附无关或重复引用。'
    '引用最多4096 UTF-8字节。要解释跨文件的事实须引用两端。数值/默认值引用须带完整赋值或参数声明，'
    '条件行为引用须带相关条件与结果，不能只抄一个数或单个词。edits 为原文替换数组，'
    '每项恰含 path、before、after，before 在当前文件唯一；最多8项、每段最多8192字节。'
    '修改仅限明确要求的常量/默认参数，其他 Python AST 行为不得变化；无需格式化，不运行代码。'
    'answers 回答修改前快照事实，edits 提交所要求修改。无修改任务的 edits 必须为 []。')

PATCH_QUESTIONS = {
    'urllib3/urllib3': '将连接池未显式配置重试时使用的默认次数从3改5，将默认退避秒数上限从120改240。保留 Retry 构造器 total=10、显式传入值和其他全部行为。',
    'tkem/cachetools': '只将 lru_cache 的默认容量128改256，同时覆盖 @lru_cache 与 @lru_cache()。保留显式 maxsize、None 无界、typed 以及所有其他装饰器行为。'}


def click(f):
    p = 'pyproject.toml'; meta = tomllib.loads(f[p])
    return [
        ('minimum_python', 'project.requires-python 的精确字符串。', meta['project']['requires-python'], [(p, None, 'requires-python = ">=3.10"')]),
        ('build_backend', 'build-system.build-backend 的精确字符串。', meta['build-system']['build-backend'], [(p, None, 'build-backend = "flit_core.buildapi"')]),
        ('copyright', 'LICENSE.txt 首行版权文字的精确字符串。', f['LICENSE.txt'].splitlines()[0], [('LICENSE.txt', None, f['LICENSE.txt'].splitlines()[0])])]


def platformdirs(f):
    p, code = 'pyproject.toml', 'src/platformdirs/__init__.py'
    return [
        ('minimum_python', 'project.requires-python 的精确字符串。', tomllib.loads(f[p])['project']['requires-python'], [(p, None, 'requires-python = ">=3.11"')]),
        ('opinion_default', '顶层 user_cache_dir 的 opinion 默认布尔值。', True, [(code, 'user_cache_dir', 'opinion: bool = True')]),
        ('ensure_exists_default', '顶层 user_cache_dir 的 ensure_exists 默认布尔值。', False, [(code, 'user_cache_dir', 'ensure_exists: bool = False')])]


def urllib(f):
    r, p = 'src/urllib3/util/retry.py', 'src/urllib3/connectionpool.py'
    return [
        ('pool_default_total', '连接池未传 retries 时使用的 Retry.DEFAULT 的 total 整数；引用默认对象与池内使用两端。', 3,
            [(r, None, 'Retry.DEFAULT = Retry(3)'),
             (p, 'HTTPConnectionPool.__init__', 'retries: Retry | bool | int | None = None'),
             (p, 'HTTPConnectionPool.__init__', 'if retries is None:\n            retries = Retry.DEFAULT')]),
        ('constructor_total', 'Retry.__init__ 自己的 total 默认整数。', 10, [(r, 'Retry.__init__', 'total: bool | int | None = 10')]),
        ('default_backoff_max', 'Retry 默认退避上限秒数整数；引用默认值和构造器使用。', 120,
            [(r, 'Retry', 'DEFAULT_BACKOFF_MAX = 120'), (r, 'Retry.__init__', 'backoff_max: float = DEFAULT_BACKOFF_MAX')])]


def urllib_edits(f):
    p = 'src/urllib3/util/retry.py'
    return [{'path': p, 'before': 'Retry.DEFAULT = Retry(3)', 'after': 'Retry.DEFAULT = Retry(5)'},
        {'path': p, 'before': 'DEFAULT_BACKOFF_MAX = 120', 'after': 'DEFAULT_BACKOFF_MAX = 240'}]


def cachetools(f):
    p, c = 'src/cachetools/func.py', 'src/cachetools/__init__.py'
    return [
        ('default_maxsize', 'lru_cache 函数签名的默认容量整数。', 128, [(p, 'lru_cache', 'def lru_cache(maxsize=128, typed=False):')]),
        ('bare_maxsize', '直接写 @lru_cache 时 callable 分支传给 LRUCache 的容量整数。', 128,
            [(p, 'lru_cache', 'elif callable(maxsize):\n        return _cache(LRUCache(128), 128, typed)(maxsize)')]),
        ('cache_base_class', 'func.py 使用的 LRUCache 在定义文件中的直接父类名称字符串；引用导入和定义两端。', 'Cache',
            [(p, None, 'from . import FIFOCache, LFUCache, LRUCache, RRCache, TTLCache, cached, keys'),
             (c, 'LRUCache', 'class LRUCache(Cache):')])]


def cache_edits(f):
    p = 'src/cachetools/func.py'
    return [{'path': p, 'before': 'def lru_cache(maxsize=128, typed=False):', 'after': 'def lru_cache(maxsize=256, typed=False):'},
        {'path': p, 'before': 'return _cache(LRUCache(128), 128, typed)(maxsize)',
         'after': 'return _cache(LRUCache(256), 256, typed)(maxsize)'}]


def httpcore(f):
    p, m = 'httpcore/_sync/connection_pool.py', 'httpcore/_models.py'
    a, b = scope(f[p], 'ConnectionPool.__init__')
    text = f[p][a:b]
    # 一段完整初始化证据同时保留参数与 min 约束，防止只引用一个默认数。
    assignments = [ast.get_source_segment(f[p], node) for node in ast.walk(ast.parse(f[p]))
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Attribute)
        and node.targets[0].attr in ('_max_connections', '_max_keepalive_connections')
        and a <= sum(map(len, f[p].splitlines(keepends=True)[:node.lineno-1])) < b]
    if len(assignments) != 3: raise ValueError('连接上限实现发生变化')
    return [
        ('effective_default_keepalive', 'ConnectionPool 默认构造参数下，最终 _max_keepalive_connections 的有效整数；须包含默认参数及上限计算证据。', 10,
            [(p, 'ConnectionPool.__init__', 'max_connections: int | None = 10'),
             (p, 'ConnectionPool.__init__', 'max_keepalive_connections: int | None = None'),
             *[(p, 'ConnectionPool.__init__', quote) for quote in assignments]]),
        ('pool_timeout_key', 'handle_request 从 timeout 映射取等待连接超时的键名字符串。', 'pool',
            [(p, 'ConnectionPool.handle_request', 'timeout = timeouts.get("pool", None)')]),
        ('default_extensions', 'Request 未传 extensions 时 self.extensions 的值，使用原生对象。', {},
            [(m, 'Request.__init__', 'extensions: Extensions | None = None'),
             (m, 'Request.__init__', 'self.extensions = {} if extensions is None else extensions')])]


def anyio(f):
    p, b = 'src/anyio/_core/_tasks.py', 'src/anyio/_backends/_asyncio.py'
    start, end = scope(f[p], 'move_on_after')
    body = f[p][start:end]
    implementation = body[body.index('    deadline = ('):].rstrip()
    return [
        ('move_on_after_starts_at_call', 'move_on_after 计时是否从函数调用时开始（而非进入上下文时），使用布尔值。', True,
            [(p, 'move_on_after', ['the timer starts when this function is\n        called, not when the context manager is entered.', implementation])]),
        ('no_task_deadline_sign', 'AsyncIOBackend.current_effective_deadline 没有当前任务时返回无穷的符号，正无穷写整数1、负无穷写整数-1。', 1,
            [(b, 'AsyncIOBackend.current_effective_deadline', 'if (task := current_task()) is None:\n            return math.inf')]),
        ('clock_expression', 'AsyncIOBackend.current_time 返回的时钟表达式精确字符串，并引用 move_on_after 使用该时钟和后端定义两端。', 'get_running_loop().time()',
            [(b, 'AsyncIOBackend.current_time', 'return get_running_loop().time()'),
             (p, 'move_on_after', '(get_async_backend().current_time() + delay) if delay is not None else math.inf')])]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--finance', required=True)
    args = parser.parse_args()
    result = build(args.sources, args.output, args.finance)
    print(json.dumps({'modelCalls': 0, 'taskCount': len(result['tasks']), 'releaseAllowed': False}))
