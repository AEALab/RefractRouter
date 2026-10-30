"""可选版本治理入口；只固定配置，再委派既有标准Gateway执行原策略。"""
from copy import deepcopy
from contextvars import ContextVar
from dataclasses import replace
from pathlib import Path
from threading import RLock,Condition
from uuid import uuid4
import fcntl
import os

from .model_gateway import ModelGateway, HttpModelCaller, GATEWAY_PROTOCOL_VERSION, package_version
from .release_governance import ReleaseStore, digest, validate_release, object_fields
from .planning_config import compile_config

CONFIG = 'refractrouter-gateway-config-v3'
ALIAS = 'refract/release'


class GovernedGateway:
    def __init__(self, config, runs_dir, *, caller_factory=None, implementation=None):
        if type(config) is not dict or set(config)-{'schemaVersion','releaseRegistry','authTokenEnv'}:
            raise ValueError('治理网关包含未知配置')
        if config['schemaVersion'] != CONFIG: raise ValueError('未知治理网关版本')
        self.store=ReleaseStore(config['releaseRegistry'],implementation=implementation)
        if config.get('authTokenEnv')!=self.store.baseline_snapshot()['configuration'].get('authTokenEnv'):
            raise ValueError('入站认证与冻结基线不一致')
        self._service_fd=os.open(self.store.root/'.service.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
        try:
            fcntl.flock(self._service_fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.runs_dir=self.store.bind_execution_root(runs_dir)
            self.store.reconcile_execution_history(self.runs_dir)
        except BaseException:
            os.close(self._service_fd);self._service_fd=None
            raise ValueError('治理服务已运行或执行目录不一致；拒绝启动第二个派发者') from None
        self.owner=uuid4().hex
        self.execution_context=ContextVar('refract-release-execution',default=None)
        self.disabled=False
        self._lifecycle=Condition();self._active=0;self._closed=False
        self.caller_factory=caller_factory
        self.gateways={};self.history_gateways={};self.lock=RLock();self.task_locks={}

    def gateway(self, release_id):
        with self.lock:
            if release_id not in self.gateways:
                snapshot=self.store.snapshot(release_id)
                validate_release(snapshot,implementation=self.store.implementation)
                cfg=snapshot['configuration']
                delegate=self.caller_factory(snapshot) if self.caller_factory else HttpModelCaller(cfg['providers'])
                def caller(action,options):
                    context=self.execution_context.get()
                    if context is None:raise ValueError('治理派发缺少任务所有权上下文')
                    try:response=delegate(action,options)
                    except Exception:
                        context['drift']=True
                        try:self.store.invalidate(release_id,actor='gateway',reason='upstream-usage-unconfirmed')
                        except Exception:self.disabled=True
                        raise
                    provider=action['model']['provider'];model=action['model']['id']
                    confirmed=(response.actual_model==snapshot['versions']['models'][model]
                        and response.provider_revision==snapshot['versions']['providers'][provider])
                    try:
                        self.store.observe_version(context['task'],release_id,{'callId':action['callId'],
                            'observedModel':response.actual_model,'observedProvider':response.provider_revision,
                            'matchesFrozenVersion':confirmed,'usageAvailable':response.usage_available})
                        if not confirmed or not response.usage_available:
                            context['drift']=True
                            self.store.invalidate(release_id,actor='gateway',reason='version-or-usage-unconfirmed')
                    except Exception:
                        self.disabled=True;context['drift']=True
                    return replace(response,price_binding_confirmed=confirmed)
                # 验证版本后再向客户端发送文本；复用核心的buffered-release诊断，不冒充即时首字。
                # 历史查看也可追加宿主事实，必须与执行复用同一个缓存所有者。
                gateway=self.history_gateways.get(release_id)
                created=gateway is None
                if created:gateway=ModelGateway(cfg,self.runs_dir/'releases'/release_id,caller)
                if self.caller_factory is None:
                    try:gateway._check_providers(compile_config(cfg['planningRouting']))
                    except Exception:
                        if created:gateway.close()
                        raise
                with gateway.lock:gateway.caller=caller
                self.history_gateways.pop(release_id,None)
                self.gateways[release_id]=gateway
            return self.gateways[release_id]

    def history_gateway(self,release_id):
        with self.lock:
            if release_id in self.gateways:return self.gateways[release_id]
            if release_id not in self.history_gateways:
                snapshot=self.store.snapshot(release_id)
                def no_dispatch(*_args,**_kwargs):raise ValueError('历史查看入口禁止模型派发')
                self.history_gateways[release_id]=ModelGateway(snapshot['configuration'],
                    self.runs_dir/'releases'/release_id,no_dispatch)
            return self.history_gateways[release_id]

    def service_info(self):
        selected=[]
        ready=not self.disabled and not self._closed
        try:
            selected=self.store.selection_versions()
            for release_id in selected:self.gateway(release_id)
        except ValueError:ready=False
        return {'status':'ready' if ready else 'not-ready','service':GATEWAY_PROTOCOL_VERSION,'version':package_version(),
            'configDigest':digest({'schema':CONFIG,'selectableReleases':selected}), 'strategies':[ALIAS], 'modelCalls':0,
            'toolExecution':False,'configurationGovernance':'versioned-explicit-trial',
            'coverage':'managed-agent-only','parentChildSharedBudgetEnforced':False}

    def models(self):
        # 治理模型是配置入口，不是第七种选模策略，也不增加工具权限或隐藏上下文。
        if self.service_info()['status']!='ready':return {'object':'list','data':[]}
        capabilities=[]
        for release_id in self.store.selection_versions():
            gateway=self.gateway(release_id)
            capabilities.append(gateway.capabilities(self.store.snapshot(release_id)['strategy']))
        shared=lambda key: sorted(set.intersection(*(set(c[key]) for c in capabilities)))
        return {'object':'list','data':[{'id':ALIAS,'object':'model','created':0,'owned_by':'refractrouter',
            'refract':{'configurationGovernance':'versioned-explicit-trial','inputModalities':['text'],
                'outputModalities':['text'],'toolExecution':'client','historyMode':'full',
                'capabilityAdmission':'selected-frozen-gateway-v2','streaming':True,
                'toolTypes':shared('toolTypes'),'verifiedRequestFeatures':shared('verifiedRequestFeatures'),
                'acceptedReasoningEfforts':shared('acceptedReasoningEfforts'),
                'contextWindow':min(c['contextWindow'] for c in capabilities),
                'maxOutputTokens':min(c['maxOutputTokens'] for c in capabilities),
                'parentChildSharedBudgetEnforced':False}}]}

    def identity(self, request, scope):
        metadata=request.get('metadata') or {}
        if type(metadata) is not dict: raise ValueError('metadata必须是对象')
        session,task=metadata.get('refract_session'),metadata.get('refract_task')
        explicit=session is not None or task is not None
        if explicit and any(type(v) is not str or not 0<len(v)<=256 for v in (session,task)):
            raise ValueError('显式任务身份必须完整')
        tail=[]
        for message in reversed(request.get('messages',[])):
            if message.get('role') != 'tool': break
            tail.append(message.get('tool_call_id'))
        known=[self.store.alias(scope,'tool',token) for token in tail if isinstance(token,str)]
        if any(known):
            if len(known)!=len(tail) or not all(known) or len(set(known))!=1:
                raise ValueError('工具续接来自不同任务或缺少版本归属')
            owner=self.store.binding(known[0])['identity']
            if explicit and (session,task)!=(owner['session'],owner['task']):
                raise ValueError('工具续接与显式任务身份矛盾')
            session,task=owner['session'],owner['task']
        elif tail and not explicit:
            raise ValueError('未知工具历史需要接入方明确新任务身份')
        elif not explicit:
            session,task=uuid4().hex,'1'
        origin=owner.get('explicit',False) if any(known) else explicit
        identity={'scope':scope,'session':session,'task':task,'explicit':origin}
        return digest({k:v for k,v in identity.items() if k!='explicit'}),identity

    def complete(self, request, *, scope='default', cancelled=lambda:False, on_text=None, on_outcome=None):
        with self._lifecycle:
            if self._closed or self.disabled:raise ValueError('治理服务已关闭或审计异常，拒绝新派发')
            self._active+=1
        try:
            return self._complete(request,scope=scope,cancelled=cancelled,on_text=on_text,on_outcome=on_outcome)
        finally:
            with self._lifecycle:self._active-=1;self._lifecycle.notify_all()

    def _complete(self, request, *, scope, cancelled, on_text, on_outcome):
        if type(request) is not dict or request.get('model')!=ALIAS:
            raise ValueError('治理入口请选择refract/release；策略由显式冻结配置决定')
        task,identity=self.identity(request,scope)
        with self.lock:guard=self.task_locks.setdefault(task,RLock())
        with guard:
            context={'task':task,'drift':False}
            token=self.execution_context.set(context)
            try:
                return self._execute_task(request,task,identity,scope=scope,
                    cancelled=lambda:context['drift'] or cancelled(),on_text=on_text,on_outcome=on_outcome)
            finally:self.execution_context.reset(token)

    def _execute_task(self,request,task,identity,*,scope,cancelled,on_text,on_outcome):
        assignment=self.store.assign(task,identity)
        self.store.claim_execution(task,self.owner)
        release_id=assignment['releaseSha256']
        gateway=self.gateway(release_id)
        snapshot=self.store.snapshot(release_id)
        caller_explicit=(request.get('metadata') or {}).get('refract_task') is not None
        if not caller_explicit and request.get('messages') and request['messages'][-1].get('role')=='tool':
            # 只恢复版本不能把匿名请求升级为可信显式身份，必须沿用原核心的历史前缀校验。
            verified=gateway._identity(request,scope)
            expected=gateway._identity({**request,'metadata':{'refract_session':identity['session'],
                'refract_task':identity['task']}},scope)
            if verified!=expected:raise ValueError('工具续接历史丢失或改变')
        self.store.claim_request(task,self.owner,digest({k:v for k,v in request.items()
            if k not in ('stream','stream_options')}))
        value=deepcopy(request)
        value['model']='refract/'+snapshot['strategy']
        value['metadata']={**(value.get('metadata') or {}),'refract_session':identity['session'],
            'refract_task':identity['task']}
        current_run=[]
        def outcome(run_id):
            current_run.append(run_id)
            self.store.bind_alias(task,scope,'outcome',run_id)
            if on_outcome is not None:on_outcome(run_id)
        def text(meta,content):
            return on_text({**meta,'model':ALIAS},content)
        try:
            result=gateway.complete(value,scope=scope,cancelled=cancelled,
                on_text=text if on_text is not None else None,on_outcome=outcome)
        finally:
            # 缓存写入细分等未知可能到核心结算时才发现，不能只依赖上游usage_available。
            for run_id in current_run:
                record=gateway.runtime.runs.get(run_id)
                if record is not None and any(c.get('status') in ('unknown-usage','reserved')
                        or c.get('price_binding_confirmed') is False for c in record['budget'].records):
                    try:self.store.invalidate(release_id,actor='gateway',reason='settlement-unconfirmed')
                    except Exception:self.disabled=True;raise
        for call in result['choices'][0]['message'].get('tool_calls',[]):
            self.store.bind_alias(task,scope,'tool',call['id'])
        if not identity['explicit'] and not result['choices'][0]['message'].get('tool_calls'):
            gateway.runtime.handle({'op':'end','runId':current_run[0]})
        result['model']=ALIAS
        return result

    def record_host_evidence(self, submitted, *, scope='default'):
        task=self.store.alias(scope,'tool',submitted.get('callId'))
        if task is None:raise ValueError('工具调用不属于当前访问域的已交付任务')
        return self.history_gateway(self.store.binding(task)['release_id']).record_host_evidence(submitted,scope=scope)

    def outcome(self, request, *, scope='default'):
        task=self.store.alias(scope,'outcome',request.get('runId'))
        if task is None:raise ValueError('结果不属于当前访问域')
        binding=self.store.binding(task)
        result=self.history_gateway(binding['release_id']).outcome(request,scope=scope)
        result['releaseBinding']={'releaseSha256':binding['release_id'],'trialId':binding['trial_id'],
            'newTasksOnly':True,'parentChildSharedBudgetEnforced':False}
        return result

    def close(self):
        with self._lifecycle:
            self._closed=True
            while self._active:self._lifecycle.wait()
        for gateway in [*self.gateways.values(),*self.history_gateways.values()]:gateway.close()
        if self._service_fd is not None:
            fcntl.flock(self._service_fd,fcntl.LOCK_UN);os.close(self._service_fd);self._service_fd=None
