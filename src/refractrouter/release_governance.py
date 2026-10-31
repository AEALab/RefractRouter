"""本机配置发布治理；不选模型、不复制预算、不执行工具或自动训练。"""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from uuid import uuid4

from .planning_config import compile_config, preview, STRATEGIES
from .development_evaluation import paired_screen
from .readonly_facts import check_json_value, strict_json as parse_json

VERSION = 'routing-release-v2'
LEGACY_VERSION = 'routing-release-v1'
EVIDENCE = 'routing-release-evidence-v1'
HASH = re.compile(r'[0-9a-f]{64}')


def encoded(value):
    check_json_value(value, maximum_bytes=16*1024*1024)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value): return hashlib.sha256(encoded(value).encode()).hexdigest()


def stored_json(raw):
    return parse_json(raw,maximum_bytes=16*1024*1024)


def core_identity():
    """版本号相同也区分实际安装源码与资源；不读取工作区、凭据或实验答卷。"""
    root = Path(__file__).parent
    files = sorted([*root.glob('*.py'), *root.glob('resources/*.json')])
    return digest({str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files})


def object_fields(value, fields, name):
    if type(value) is not dict or set(value) != set(fields):
        raise ValueError(f'{name}字段不完整或存在未知字段')


def frozen_release(config, versions, *, implementation=None, publication_id=None, schema_version=VERSION):
    """冻结既有Gateway v2和精确身份声明；声明本身不是资格证据。"""
    if (type(config) is not dict or set(config)-{'schemaVersion','planningRouting','providers','authTokenEnv'}
            or not {'schemaVersion','planningRouting','providers'}<=set(config)):
        raise ValueError('发布配置字段不完整或存在未知字段')
    if 'authTokenEnv' in config and (type(config['authTokenEnv']) is not str
            or re.fullmatch(r'[A-Z][A-Z0-9_]*',config['authTokenEnv']) is None):
        raise ValueError('入站认证只能使用环境变量名称')
    if config['schemaVersion'] != 'refractrouter-gateway-config-v2':
        raise ValueError('治理入口只接受已接通的Gateway v2文本协议')
    compiled = compile_config(config['planningRouting'])
    identity=implementation or core_identity()
    if type(identity) is not str or HASH.fullmatch(identity) is None:raise ValueError('核心实现需要精确SHA256')
    publication=publication_id or uuid4().hex
    if type(publication) is not str or not 0<len(publication)<=128:raise ValueError('发布版本名称无效')
    strategy = compiled['strategy']
    if not next(r['available'] for r in preview(config['planningRouting'])['strategies'] if r['id'] == strategy):
        raise ValueError('发布配置的策略尚不可执行')
    if type(versions) is not dict or set(versions) != {'providers', 'models', 'outputSemantics'}:
        raise ValueError('必须固定provider与模型精确版本声明')
    if set(versions['providers']) != set(config['providers']) or set(versions['models']) != set(compiled['models']):
        raise ValueError('版本声明必须完整覆盖provider和模型')
    for value in [*versions['providers'].values(), *versions['models'].values()]:
        if (type(value) is not str or not 0 < len(value) <= 256
                or value.strip().lower() in {'unknown','unverified','latest','none','unspecified','未知','待复核'}):
            raise ValueError('版本未知时不能生成可治理发布')
    if set(versions['outputSemantics']) != set(config['providers']):
        raise ValueError('必须提供每个provider输出语义的审核来源')
    for semantics in versions['outputSemantics'].values():
        object_fields(semantics, ('parameter','scope','sourceSha256'), '输出语义')
        if (semantics['scope'] not in ('answer-and-reasoning-total','answer-only','unknown')
                or type(semantics['sourceSha256']) is not str or HASH.fullmatch(semantics['sourceSha256']) is None):
            raise ValueError('原生费用语义需要明确范围及审核来源哈希')
    from urllib.parse import urlsplit
    for provider in config['providers'].values():
        if (type(provider) is not dict or set(provider) - {
                'baseURL', 'apiKeyEnv', 'timeoutSeconds', 'tokenLimitParameter', 'requestOptions'}):
            raise ValueError('provider必须使用环境变量凭据，不能冻结密钥或任意请求头')
        url = urlsplit(provider.get('baseURL', ''))
        if (url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password
                or url.query or url.fragment):
            raise ValueError('provider地址不能携带认证或不透明参数')
        if provider.get('apiKeyEnv') is not None and re.fullmatch(r'[A-Z][A-Z0-9_]*', provider['apiKeyEnv']) is None:
            raise ValueError('只允许凭据环境变量名称')
        if set(provider.get('requestOptions', {})) - {'thinking','reasoning_effort','temperature','top_p'}:
            raise ValueError('provider选项不能覆盖协议或凭据')
        if schema_version==VERSION and provider.get('tokenLimitParameter','max_tokens') not in ('max_tokens','max_completion_tokens'):
            raise ValueError('当前Chat网关未接通该输出参数')
    if schema_version not in (VERSION,LEGACY_VERSION):raise ValueError('未知发布快照版本')
    if schema_version==LEGACY_VERSION:
        # 只复核原历史摘要，不将旧资格或容量声明重新解释为新合同。
        budget_verified = all(config['providers'][m.provider].get('tokenLimitParameter') == 'max_completion_tokens'
            and versions['outputSemantics'][m.provider]['parameter'] == 'max_completion_tokens'
            and versions['outputSemantics'][m.provider]['scope'] == 'answer-and-reasoning-total'
            and type(m.max_output_tokens) is int and 0 < m.max_output_tokens <= 8192 for m in compiled['models'].values())
    else:
        budget_verified=all(m.output_budget['scope']!='unknown'
            and m.output_budget['scope']==versions['outputSemantics'][m.provider]['scope']
            and versions['outputSemantics'][m.provider]['parameter']==config['providers'][m.provider].get('tokenLimitParameter','max_tokens')
            and m.output_budget['parameter'] in ('host-maxTokens',versions['outputSemantics'][m.provider]['parameter'])
            for m in compiled['models'].values())
    common = deepcopy(config)
    common['planningRouting'].pop('defaultStrategy', None)
    units={m.billing_unit for m in compiled['models'].values()}
    def paid_jev(value):
        if type(value) is dict:return value.get('type')=='jev' or any(paid_jev(v) for v in value.values())
        if type(value) in (list,tuple):return any(paid_jev(v) for v in value)
        return False
    if any(paid_jev(compiled.get(name)) for name in ('task','stage','composite','advisor','escalation')):units.add('CNY')
    payload = {'schemaVersion': schema_version, 'configuration': deepcopy(config), 'versions': deepcopy(versions),
        'implementationSha256': identity, 'strategy': strategy,'publicationId':publication,
        'billingUnit': compiled['unit'],
        'billingUnits': sorted(units),
        'contextSha256': digest({'configuration': common, 'versions': versions,
            'implementationSha256':identity}),
        'nativeBudgetVerified': budget_verified, 'coverage': 'managed-agent-only',
        'parentChildSharedBudgetEnforced': False}
    return {**payload, 'releaseSha256': digest(payload)}


def validate_release(value, *, implementation=None):
    object_fields(value, ('schemaVersion','configuration','versions','implementationSha256','strategy','billingUnit','billingUnits','publicationId',
        'contextSha256','nativeBudgetVerified','coverage','parentChildSharedBudgetEnforced','releaseSha256'), '发布快照')
    expected = frozen_release(value['configuration'], value['versions'], implementation=value['implementationSha256'],
        publication_id=value['publicationId'],schema_version=value['schemaVersion'])
    if expected != value:
        raise ValueError('发布快照摘要或派生声明不符')
    if implementation is not None and value['implementationSha256'] != implementation:
        raise ValueError('核心版本漂移，资格待复核')
    return deepcopy(value)


def component_releases(release):
    """绑定Composite真正使用的Task与每一种Stage初始模型，不能借用顶层同名设置。"""
    raw=deepcopy(release['configuration']); planning=raw['planningRouting']
    compiled=compile_config(planning); composite=compiled['composite']
    task=composite['task']
    task_config=deepcopy(raw); target=task_config['planningRouting'];target['defaultStrategy']='task'
    if task['mode']=='pool':target['task']={k:deepcopy(v) for k,v in task.items() if k!='mode'}
    elif 'task' in target:target.pop('task')
    task_release=frozen_release(task_config,release['versions'],implementation=release['implementationSha256'],
        schema_version=release['schemaVersion'])
    stages={}
    for initial in dict.fromkeys([*task['pool'],compiled['roles']['efficient']]):
        if initial==composite['takeover']:continue
        stage_config=deepcopy(raw); target=stage_config['planningRouting'];target['defaultStrategy']='stage'
        target['roles']['efficient']=initial;target['roles']['capable']=composite['takeover']
        stage=composite['stage']
        if stage['mode']=='rules':
            if target['schemaVersion'] in ('refractagent-planning-v5','refractagent-planning-v6',
                    'refractagent-planning-v7','refractagent-planning-v8'):target['stage']={'mode':'rules'}
            target['parameters']={**target.get('parameters',{}),**{k:stage[k] for k in ('window','threshold','holdTurns')}}
        else:target['stage']=deepcopy(stage)
        stages[initial]=frozen_release(stage_config,release['versions'],implementation=release['implementationSha256'],
            schema_version=release['schemaVersion'])
    return {'task':task_release,'stage':stages}


def qualification(release, evidence, *, implementation=None):
    """验收真实独立配对的声明及数值；来源真实性仍由维护者审计，不伪称签名认证。"""
    validate_release(release)
    reasons = []
    if release['schemaVersion']==LEGACY_VERSION:reasons.append('legacy-output-contract-requires-refreeze')
    if not release['nativeBudgetVerified']: reasons.append('native-output-budget-unverified-223')
    if implementation is not None and release['implementationSha256'] != implementation:
        reasons.append('implementation-drift')
    if evidence is None:
        reasons.append('missing-independent-evidence')
        return {'qualified': False, 'reasons': reasons, 'releaseSha256': release['releaseSha256']}
    check_json_value(evidence,maximum_bytes=16*1024*1024)
    object_fields(evidence, ('schemaVersion','kind','strategy','contextSha256','sourceAuditSha256',
        'toolsSha256','hostSha256','deliverySha256','independenceAudited','hiddenIsolationAudited',
        'criticalRegressions','rows','componentEvidence','billingUnit','costAuditSha256','costScope',
        'researchScoringReportedSeparately','incrementalRows'), '发布资格证据')
    for key in ('sourceAuditSha256','toolsSha256','hostSha256','deliverySha256','costAuditSha256'):
        if type(evidence[key]) is not str or HASH.fullmatch(evidence[key]) is None:
            raise ValueError('资格证据需要固定来源与同工具交付摘要')
    if (evidence['schemaVersion'] != EVIDENCE or evidence['kind'] != 'empirical-independent-holdout'
            or evidence['strategy'] != release['strategy'] or evidence['contextSha256'] != release['contextSha256']
            or evidence['independenceAudited'] is not True or evidence['hiddenIsolationAudited'] is not True):
        reasons.append('evidence-scope-or-independence-unqualified')
    if (evidence['billingUnit'] != release['billingUnit'] or release['billingUnit'] not in ('CNY','USD','AFP')
            or release['billingUnits'] != [release['billingUnit']]
            or evidence['costScope'] != 'all-execution-routing-online-review-attempts'
            or evidence['researchScoringReportedSeparately'] is not True):
        reasons.append('cost-unit-or-coverage-unqualified')
    if type(evidence['criticalRegressions']) is not int or evidence['criticalRegressions'] != 0:
        reasons.append('critical-regression')
    screen = paired_screen(evidence['rows'])
    if not screen['qualityIntervalWithinMargin']: reasons.append('quality-precision-or-loss')
    if not screen['costTargetObserved']: reasons.append('full-cost-target')
    components = evidence['componentEvidence']
    if release['strategy'] == 'composite':
        if type(components) is not dict or set(components) != {'task','stage'}:
            reasons.append('missing-qualified-components')
        else:
            effective=component_releases(release)
            task_verdict=qualification(effective['task'],components['task'],implementation=implementation)
            if not task_verdict['qualified']:reasons.append('task-component-unqualified')
            stages=components['stage']
            if type(stages) is not dict or not effective['stage'] or set(stages)!=set(effective['stage']):
                reasons.append('stage-components-incomplete')
                stages={}
            pairs=[('task',components['task'])]
            for initial,component in stages.items():
                verdict=qualification(effective['stage'][initial],component,implementation=implementation)
                if not verdict['qualified']:reasons.append('stage-component-unqualified')
                pairs.append(('stage',component))
            for strategy,component in pairs:
                if any(component[key] != evidence[key] for key in ('toolsSha256','hostSha256','deliverySha256')):
                    reasons.append(strategy+'-component-boundary-drift')
            incremental=evidence['incrementalRows']
            if type(incremental) is not dict or set(incremental)!={'task','stage'}:
                reasons.append('missing-composite-incremental-comparison')
            else:
                expected={r['taskId']:r for r in evidence['rows']}
                for strategy,rows in incremental.items():
                    result=paired_screen(rows)
                    if strategy=='task':baseline=components['task']
                    else:
                        primary=compile_config(release['configuration']['planningRouting'])['roles']['efficient']
                        baseline=stages.get(primary)
                    baseline_rows={r['taskId']:r for r in baseline['rows']} if baseline is not None else {}
                    aligned=(len(rows)==len(expected) and {r['taskId'] for r in rows}==set(expected)
                        and all(all(r[k]==expected[r['taskId']][k] for k in (
                            'half','candidatePassed','candidateCost','completedPair','knownCost')) for r in rows)
                        and set(expected)<=set(baseline_rows)
                        and all(r['baselinePassed']==baseline_rows[r['taskId']]['candidatePassed']
                            and r['baselineCost']==baseline_rows[r['taskId']]['candidateCost']
                            and all(baseline_rows[r['taskId']][k]==expected[r['taskId']][k]
                                for k in ('half','baselinePassed','baselineCost')) for r in rows if r['taskId'] in baseline_rows))
                    if (not aligned or not result['qualityIntervalWithinMargin'] or not result['batchCostComparable']
                            or result['savingsFraction'] is None or result['savingsFraction']<=0
                            or len(result['halfSavings'])!=2 or any(h is None or h<=0 for h in result['halfSavings'])):
                        reasons.append(strategy+'-incremental-benefit-unqualified')
    elif components != {} or evidence['incrementalRows']!={}:
        raise ValueError('单策略不能附加组合资格以绕过边界')
    return {'qualified': not reasons, 'reasons': reasons, 'releaseSha256': release['releaseSha256'],
        'evidenceSha256': digest(evidence), 'screen': screen}


class ReleaseStore:
    """持久配置与任务归属；不保存或释放模型费用，不自动重发任务。"""
    def __init__(self, root, *, implementation=None):
        self.root = Path(root).resolve(); self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.root/'releases.sqlite3'
        self.implementation = implementation or core_identity()
        if self.path.is_symlink(): raise ValueError('发布账本不能是符号链接')
        # 初始化只由显式create完成；缺失数据库不自动创建，避免重启重置试用次数。
        if not self.path.is_file(): raise ValueError('发布账本未初始化；须显式创建')
        with self.transaction(write=False): pass

    @classmethod
    def create(cls, root, baseline, *, actor, implementation=None):
        identity = implementation or core_identity()
        validate_release(baseline, implementation=identity)
        if baseline['schemaVersion']!=VERSION:
            raise ValueError('历史发布快照只读；新基线需要按当前输出合同重新冻结')
        if not baseline['nativeBudgetVerified']:
            raise ValueError('默认路线原生费用语义未验证，见#223，不能无声缩输出')
        root=Path(root).resolve(); root.mkdir(parents=True,exist_ok=True,mode=0o700)
        path=root/'releases.sqlite3'
        marker=os.open(root/'.initialized',os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
        with os.fdopen(marker,'wb') as stream:
            stream.write(VERSION.encode()); stream.flush(); os.fsync(stream.fileno())
        fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600); os.close(fd)
        try:
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE versions (id TEXT PRIMARY KEY, snapshot TEXT NOT NULL, evidence TEXT, qualification TEXT NOT NULL)')
                db.execute('CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
                db.execute('CREATE TABLE trials (id TEXT PRIMARY KEY, release_id TEXT NOT NULL, max_tasks INTEGER NOT NULL, expires TEXT NOT NULL, used INTEGER NOT NULL, active INTEGER NOT NULL)')
                db.execute('CREATE TABLE assignments (task TEXT PRIMARY KEY, release_id TEXT NOT NULL, identity TEXT NOT NULL, trial_id TEXT)')
                db.execute('CREATE TABLE aliases (scope TEXT NOT NULL, kind TEXT NOT NULL, token TEXT NOT NULL, task TEXT NOT NULL, PRIMARY KEY(scope,kind,token))')
                db.execute('CREATE TABLE execution_owners (task TEXT PRIMARY KEY, owner TEXT NOT NULL)')
                db.execute('CREATE TABLE request_claims (task TEXT NOT NULL, request_sha TEXT NOT NULL, owner TEXT NOT NULL, PRIMARY KEY(task,request_sha))')
                db.execute('CREATE TABLE events (seq INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, actor TEXT NOT NULL, payload TEXT NOT NULL, at TEXT NOT NULL)')
                db.execute('INSERT INTO versions VALUES (?,?,?,?)',(baseline['releaseSha256'],encoded(baseline),None,'baseline-existing-explicit'))
                db.execute('INSERT INTO settings VALUES (?,?)',('default',baseline['releaseSha256']))
                db.execute('INSERT INTO settings VALUES (?,?)',('baseline',baseline['releaseSha256']))
                db.execute('INSERT INTO events(kind,actor,payload,at) VALUES (?,?,?,?)',('initialize',actor,encoded({'baseline':baseline['releaseSha256']}),datetime.now(timezone.utc).isoformat()))
                db.execute('PRAGMA user_version=1')
        except BaseException:
            # 失败文件保持，下一次不能无声覆盖已存在的发布状态。
            raise
        return cls(root, implementation=identity)

    @contextmanager
    def transaction(self, *, write=True):
        db=sqlite3.connect(self.path.as_uri()+'?mode=rw',uri=True,isolation_level=None,timeout=5)
        db.row_factory=sqlite3.Row
        try:
            if db.execute('PRAGMA user_version').fetchone()[0] != 1: raise ValueError('发布账本版本损坏')
            db.execute('PRAGMA synchronous=FULL'); db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            yield db
            db.execute('COMMIT')
        except BaseException:
            if db.in_transaction: db.execute('ROLLBACK')
            raise
        finally: db.close()

    def event(self, db, kind, actor, payload):
        if type(actor) is not str or not 0 < len(actor) <= 128: raise ValueError('需要明确本机操作者')
        db.execute('INSERT INTO events(kind,actor,payload,at) VALUES (?,?,?,?)',
            (kind,actor,encoded(payload),datetime.now(timezone.utc).isoformat()))

    def add(self, release, evidence=None, *, actor):
        validate_release(release)
        verdict=qualification(release,evidence,implementation=self.implementation)
        with self.transaction() as db:
            db.execute('INSERT INTO versions VALUES (?,?,?,?)',(release['releaseSha256'],encoded(release),
                encoded(evidence) if evidence is not None else None,encoded(verdict)))
            self.event(db,'add',actor,{'release':release['releaseSha256'],'qualified':verdict['qualified']})
        return verdict

    def snapshot(self, release_id):
        with self.transaction(write=False) as db:
            row=db.execute('SELECT * FROM versions WHERE id=?',(release_id,)).fetchone()
            if row is None: raise ValueError('发布版本不存在')
            return validate_release(stored_json(row['snapshot']))

    def start_trial(self, release_id, *, max_tasks, expires, actor, explicit=False):
        if explicit is not True or type(max_tasks) is not int or not 1<=max_tasks<=100:
            raise ValueError('试用必须明确开启并限制1至100个新任务')
        deadline=datetime.fromisoformat(expires)
        if deadline.tzinfo is None or deadline<=datetime.now(timezone.utc): raise ValueError('试用期限无效')
        with self.transaction() as db:
            row=db.execute('SELECT * FROM versions WHERE id=?',(release_id,)).fetchone()
            if row is None: raise ValueError('发布版本不存在')
            if row['qualification']=='pending-revalidation': raise ValueError('资格待复核，不能重新开启试用')
            release=stored_json(row['snapshot'])
            baseline_id=db.execute('SELECT value FROM settings WHERE key=?',('baseline',)).fetchone()[0]
            baseline=stored_json(db.execute('SELECT snapshot FROM versions WHERE id=?',(baseline_id,)).fetchone()[0])
            if release['configuration'].get('authTokenEnv')!=baseline['configuration'].get('authTokenEnv'):
                raise ValueError('试用不能改变当前服务的入站认证边界')
            evidence=stored_json(row['evidence']) if row['evidence'] else None
            verdict=qualification(release,evidence,implementation=self.implementation)
            if not verdict['qualified']: raise ValueError('发布资格未通过：'+','.join(verdict['reasons']))
            if db.execute('SELECT 1 FROM trials WHERE active=1').fetchone(): raise ValueError('已有活动试用，不自动重置额度')
            token=digest({'release':release_id,'at':datetime.now(timezone.utc).isoformat(),'actor':actor})
            db.execute('INSERT INTO trials VALUES (?,?,?,?,?,?)',(token,release_id,max_tasks,expires,0,1))
            self.event(db,'start-trial',actor,{'trial':token,'release':release_id,'maxTasks':max_tasks,'expires':expires})
            return token

    def stop_trial(self, *, actor, reason):
        with self.transaction() as db:
            db.execute('UPDATE trials SET active=0 WHERE active=1')
            self.event(db,'stop-trial',actor,{'reason':reason,'unknownUsageReleased':False})

    def invalidate(self, release_id, *, actor, reason):
        with self.transaction() as db:
            if not db.execute('SELECT 1 FROM versions WHERE id=?',(release_id,)).fetchone(): raise ValueError('发布版本不存在')
            db.execute('UPDATE versions SET qualification=? WHERE id=?',('pending-revalidation',release_id))
            db.execute('UPDATE trials SET active=0 WHERE release_id=?',(release_id,))
            self.event(db,'invalidate',actor,{'release':release_id,'reason':reason,'inflightMustSettle':True})

    def assign(self, task, identity):
        if type(task) is not str or HASH.fullmatch(task) is None: raise ValueError('任务归属需要精确哈希')
        with self.transaction() as db:
            prior=db.execute('SELECT * FROM assignments WHERE task=?',(task,)).fetchone()
            if prior:
                if prior['identity'] != encoded(identity): raise ValueError('任务身份冲突')
                return {'releaseSha256':prior['release_id'],'trialId':prior['trial_id'],'existing':True}
            default=db.execute('SELECT value FROM settings WHERE key=?',('default',)).fetchone()[0]
            trial=db.execute('SELECT * FROM trials WHERE active=1 ORDER BY rowid DESC LIMIT 1').fetchone()
            chosen,token=default,None
            if trial:
                trial_snapshot=stored_json(db.execute('SELECT snapshot FROM versions WHERE id=?',(trial['release_id'],)).fetchone()[0])
                if trial_snapshot['schemaVersion']==LEGACY_VERSION:
                    raise ValueError('历史发布试用需明确重新冻结；保留原资格、次数与路线，不自动回退')
                expired=datetime.fromisoformat(trial['expires'])<=datetime.now(timezone.utc)
                row=db.execute('SELECT * FROM versions WHERE id=?',(trial['release_id'],)).fetchone()
                pending=row['qualification']=='pending-revalidation'
                if not expired and trial['used']<trial['max_tasks'] and not pending:
                    release=stored_json(row['snapshot'])
                    evidence=stored_json(row['evidence']) if row['evidence'] else None
                    if qualification(release,evidence,implementation=self.implementation)['qualified']:
                        chosen,token=trial['release_id'],trial['id']
                        db.execute('UPDATE trials SET used=used+1 WHERE id=?',(token,))
                    else: db.execute('UPDATE trials SET active=0 WHERE id=?',(trial['id'],))
                else: db.execute('UPDATE trials SET active=0 WHERE id=?',(trial['id'],))
            row=db.execute('SELECT snapshot,qualification FROM versions WHERE id=?',(chosen,)).fetchone()
            if stored_json(row['snapshot'])['schemaVersion']==LEGACY_VERSION:
                raise ValueError('历史默认发布需明确重新冻结；不自动改变路线')
            validate_release(stored_json(row['snapshot']),implementation=self.implementation)
            if row['qualification']=='pending-revalidation': raise ValueError('默认配置版本待复核，拒绝新任务')
            db.execute('INSERT INTO assignments VALUES (?,?,?,?)',(task,chosen,encoded(identity),token))
            self.event(db,'assign','gateway',{'task':task,'release':chosen,'trial':token})
            return {'releaseSha256':chosen,'trialId':token,'existing':False}

    def history(self):
        with self.transaction(write=False) as db:
            return {'schemaVersion':VERSION,'versions':[dict(r) for r in db.execute('SELECT id,qualification FROM versions')],
                'trials':[dict(r) for r in db.execute('SELECT * FROM trials')],
                'assignments':[dict(r) for r in db.execute('SELECT * FROM assignments')],
                'events':[dict(r) for r in db.execute('SELECT * FROM events ORDER BY seq')],
                'parentChildSharedBudgetEnforced':False,'coverage':'managed-agent-only'}

    def binding(self, task):
        with self.transaction(write=False) as db:
            row=db.execute('SELECT * FROM assignments WHERE task=?',(task,)).fetchone()
            if row is None: raise ValueError('任务版本归属不存在')
            return {**dict(row),'identity':stored_json(row['identity'])}

    def bind_execution_root(self, root):
        root=Path(root).resolve()
        with self.transaction() as db:
            previous=db.execute('SELECT value FROM settings WHERE key=?',('executionRoot',)).fetchone()
            if previous:
                bound=stored_json(previous['value'])
                marker=root/'.governed-root'
                if (bound['path']!=str(root) or not marker.is_file() or marker.is_symlink()
                        or marker.read_text()!=bound['nonce']):
                    raise ValueError('执行目录改变或历史根标记丢失；不能重建费用与派发历史')
            else:
                root.mkdir(parents=True,exist_ok=True,mode=0o700)
                if any(root.iterdir()):raise ValueError('首次治理需要全新执行目录；不自动迁移旧账本')
                nonce=uuid4().hex
                fd=os.open(root/'.governed-root',os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
                with os.fdopen(fd,'w') as stream:stream.write(nonce);stream.flush();os.fsync(stream.fileno())
                db.execute('INSERT INTO settings VALUES (?,?)',('executionRoot',encoded({'path':str(root),'nonce':nonce})))
        return root

    def claim_execution(self, task, owner):
        with self.transaction() as db:
            if not db.execute('SELECT 1 FROM assignments WHERE task=?',(task,)).fetchone():
                raise ValueError('派发任务没有固定版本归属')
            previous=db.execute('SELECT owner FROM execution_owners WHERE task=?',(task,)).fetchone()
            if previous and previous['owner']!=owner:
                raise ValueError('旧进程任务需核对；不得自动重新派发')
            if previous is None:
                db.execute('INSERT INTO execution_owners VALUES (?,?)',(task,owner))
                self.event(db,'claim-execution','gateway',{'task':task,'owner':owner})

    def claim_request(self, task, owner, request_sha):
        with self.transaction() as db:
            previous=db.execute('SELECT owner FROM execution_owners WHERE task=?',(task,)).fetchone()
            if previous is None or previous['owner']!=owner:raise ValueError('请求没有本进程派发所有权')
            if db.execute('SELECT 1 FROM request_claims WHERE task=? AND request_sha=?',(task,request_sha)).fetchone():
                raise ValueError('相同请求已有派发记录；不得自动重新派发')
            db.execute('INSERT INTO request_claims VALUES (?,?,?)',(task,request_sha,owner))
            self.event(db,'claim-request','gateway',{'task':task,'requestSha256':request_sha,'owner':owner})

    def observe_version(self, task, release_id, observation):
        with self.transaction() as db:
            row=db.execute('SELECT release_id FROM assignments WHERE task=?',(task,)).fetchone()
            if row is None or row['release_id']!=release_id:raise ValueError('版本观测不属于原任务')
            self.event(db,'version-observed','gateway',{'task':task,'release':release_id,**observation})

    def reconcile_execution_history(self, root):
        """重启只读旧财务记录，未确认用量使资格待核，不补记或释放原费用。"""
        root=Path(root).resolve()
        with self.transaction() as db:
            pending=set()
            rows=db.execute('SELECT aliases.token,assignments.release_id FROM aliases JOIN assignments '
                'ON aliases.task=assignments.task WHERE aliases.kind=?',('outcome',)).fetchall()
            for row in rows:
                if HASH.fullmatch(row['token']) is None or HASH.fullmatch(row['release_id']) is None:
                    raise ValueError('历史执行引用损坏')
                path=root/'releases'/row['release_id']/'planning'/(row['token']+'.json')
                if (not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root)):
                    raise ValueError('历史执行记录丢失，不重建或重新派发')
                record=json.loads(path.read_bytes())
                if any(c.get('status') in ('unknown-usage','reserved') or c.get('price_binding_confirmed') is False
                        for c in record['calls']):pending.add(row['release_id'])
            for release_id in pending:
                row=db.execute('SELECT qualification FROM versions WHERE id=?',(release_id,)).fetchone()
                if row['qualification']!='pending-revalidation':
                    db.execute('UPDATE versions SET qualification=? WHERE id=?',('pending-revalidation',release_id))
                    db.execute('UPDATE trials SET active=0 WHERE release_id=?',(release_id,))
                    self.event(db,'restart-pending','gateway',{'release':release_id,'unknownUsageReleased':False})

    def selection_versions(self):
        """只读可被分配的新任务版本；不消耗试用次数，不执行影子模型答卷。"""
        with self.transaction(write=False) as db:
            default=db.execute('SELECT value FROM settings WHERE key=?',('default',)).fetchone()[0]
            row=db.execute('SELECT qualification FROM versions WHERE id=?',(default,)).fetchone()
            if row['qualification']=='pending-revalidation': raise ValueError('默认配置待复核')
            snapshot=stored_json(db.execute('SELECT snapshot FROM versions WHERE id=?',(default,)).fetchone()[0])
            if snapshot['schemaVersion']==LEGACY_VERSION:raise ValueError('历史默认发布需明确重新冻结')
            selected=[default]
            trial=db.execute('SELECT * FROM trials WHERE active=1 ORDER BY rowid DESC LIMIT 1').fetchone()
            if trial:
                candidate=stored_json(db.execute('SELECT snapshot FROM versions WHERE id=?',(trial['release_id'],)).fetchone()[0])
                if candidate['schemaVersion']==LEGACY_VERSION:raise ValueError('历史发布试用需明确重新冻结')
            if trial and trial['used']<trial['max_tasks'] and datetime.fromisoformat(trial['expires'])>datetime.now(timezone.utc):
                row=db.execute('SELECT * FROM versions WHERE id=?',(trial['release_id'],)).fetchone()
                if row['qualification']!='pending-revalidation' and qualification(stored_json(row['snapshot']),
                        stored_json(row['evidence']) if row['evidence'] else None,
                        implementation=self.implementation)['qualified']:
                    selected.append(trial['release_id'])
            return list(dict.fromkeys(selected))

    def baseline_snapshot(self):
        with self.transaction(write=False) as db:
            baseline=db.execute('SELECT value FROM settings WHERE key=?',('baseline',)).fetchone()[0]
            row=db.execute('SELECT snapshot FROM versions WHERE id=?',(baseline,)).fetchone()
            return validate_release(stored_json(row['snapshot']))

    def execution_records(self):
        """管理端只读索引；费用仍以原核心文件为唯一依据。"""
        with self.transaction(write=False) as db:
            bound=db.execute('SELECT value FROM settings WHERE key=?',('executionRoot',)).fetchone()
            root=stored_json(bound[0]) if bound else None
            rows=[dict(r) for r in db.execute('SELECT assignments.*,aliases.token AS run_id FROM assignments '
                'LEFT JOIN aliases ON assignments.task=aliases.task AND aliases.kind="outcome"')]
            return {'root':root,'records':rows}

    def alias(self, scope, kind, token):
        with self.transaction(write=False) as db:
            row=db.execute('SELECT task FROM aliases WHERE scope=? AND kind=? AND token=?',(scope,kind,token)).fetchone()
            return row['task'] if row else None

    def bind_alias(self, task, scope, kind, token):
        if kind not in ('tool','outcome') or type(token) is not str or not 0<len(token)<=256:
            raise ValueError('任务续接引用不合法')
        if kind=='outcome' and HASH.fullmatch(token) is None:raise ValueError('结果引用需要精确运行哈希')
        with self.transaction() as db:
            owner=db.execute('SELECT identity FROM assignments WHERE task=?',(task,)).fetchone()
            if owner is None or stored_json(owner['identity'])['scope'] != scope:
                raise ValueError('任务不属于当前访问域')
            previous=db.execute('SELECT task FROM aliases WHERE scope=? AND kind=? AND token=?',(scope,kind,token)).fetchone()
            if previous and previous['task'] != task: raise ValueError('续接ID冲突，不能跨版本覆盖')
            if previous is None:
                db.execute('INSERT INTO aliases VALUES (?,?,?,?)',(scope,kind,token,task))
                self.event(db,'bind-'+kind,'gateway',{'task':task,'token':token,'scope':scope})

    def rollback(self, *, actor, reason):
        """回到显式基线，只影响新归属；旧任务及其原费用记录完全保留。"""
        with self.transaction() as db:
            baseline=db.execute('SELECT value FROM settings WHERE key=?',('baseline',)).fetchone()[0]
            row=db.execute('SELECT * FROM versions WHERE id=?',(baseline,)).fetchone()
            validate_release(stored_json(row['snapshot']),implementation=self.implementation)
            if row['qualification']=='pending-revalidation': raise ValueError('基线已失效，不能冒充安全回滚')
            db.execute('UPDATE trials SET active=0 WHERE active=1')
            db.execute('UPDATE settings SET value=? WHERE key=?',(baseline,'default'))
            self.event(db,'rollback',actor,{'baseline':baseline,'reason':reason,
                'newTasksOnly':True,'unknownUsageReleased':False,'oldAssignmentsChanged':False})
        return baseline
