"""node-as-tool 当日开发先导：三路线、真实宿主、既有 DAG 调度和可复核事实。"""
from collections import Counter
from copy import deepcopy
from dataclasses import asdict, replace, dataclass
from decimal import Decimal, ROUND_CEILING
import hashlib
import json
from pathlib import Path
import random
from threading import RLock
import subprocess
import time

from .compact_planning import COMPACT_PLANNER_SYSTEM, compile_compact
from .openai_compatible import ChatResponse, OpenAICompatibleClient
from .planning_config import compile_config
from .quality_runtime import FINAL_SYSTEM, parse_delivery
from .quality_study import check_output, digest, execution_payload
from .schemas import ModelSpec
from .task_budget import TaskCallBudget, request_input_bound
from .task_execution import execute_nodes
from .task_scheduling import ExecutionPolicy

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "node-tool-three-arm-pilot-v2"
RATE = Decimal(".05")
ARMS = ("one-shot", "node-as-tool", "dag")
PROMPTS = {"existing-contract": FINAL_SYSTEM, "explicit-verification": FINAL_SYSTEM +
    "交付前逐项复核计算、版本替代、必要条件与来源支持。证据不足时明确未证明，不靠猜测补齐。正文和字段必须一致。"}
NODE_HINT = "可按需调用 refract_expert 分析材料、核对约束或综合结论。复杂子问题可委派，不必机械拆分；专家结果仍需自行核对。最终按原交付合同回答。"
# 使用模型目录的完整输出容量；思考与正文共享额度，不再用研究自设的小额度截断。
from .ark_plan import catalog
MODEL_OUTPUT = next(m["max_output_tokens"] for m in catalog()["models"] if m["model_id"] == "deepseek-v4-flash")
CAPS = {stage: {"input": 32768 if stage == "expert" else 600000, "output": MODEL_OUTPUT}
        for stage in ("main", "expert", "planner", "worker", "final")}
APPROVED_AFP = 286
APPROVED_CALLS = 135


@dataclass(frozen=True)
class PilotModel(ModelSpec):
    unrestricted_execution_output: bool = True


def carry_in(paths):
    entries=[]
    for name in paths:
        path=Path(name).resolve()
        if not path.is_relative_to(ROOT):
            raise ValueError("历史用量证据必须位于当前研究工作区")
        record=json.loads(path.read_text())
        if record.get("simulated") is not False:
            raise ValueError("不能把演练当成历史真实用量")
        calls=sum(c["status"] != "cancelled-before-dispatch" for r in record["runs"] for c in r["calls"])
        cost=sum(Decimal(str(c["charged"])) for r in record["runs"] for c in r["calls"])
        if calls != record["realModelCalls"] or abs(float(cost)-record["actualOrReservedAfp"]) > 1e-8:
            raise ValueError("历史汇总与原始调用账本不一致")
        entries.append({"path":str(path.relative_to(ROOT)),"sha256":file_hash(path),
            "realModelCalls":calls,"actualOrReservedAfp":float(cost),"protocolSha256":record["protocolSha256"]})
    if len({v["path"] for v in entries}) != len(entries):
        raise ValueError("历史批次不得重复累计")
    return entries


def cumulative_admission(result, case):
    # 原先导的失败调用和未知用量预留持续占用同一人类批准额度。
    if result["cumulativeRealModelCalls"] + case["maxModelCalls"] > APPROVED_CALLS:
        return "stopped-approved-call-limit"
    remaining=Decimal(str(APPROVED_AFP))-Decimal(str(result["cumulativeActualOrReservedAfp"]))
    if remaining <= 0:
        return "stopped-approved-afp-limit"
    # 只给实际派发保留足额容量；逐调用预留在 Python 核心执行。
    # 不能用所有未来请求都输出到模型最大容量的总和，提前阻断整个研究。
    case["unconstrainedAfpUpperBound"]=case["afpUpperBound"]
    case["afpUpperBound"]=min(case["afpUpperBound"],float(remaining))
    case["planningConfig"]["maxProductionCostByUnit"]["AFP"]=case["afpUpperBound"]
    return None


def write(path, value):
    path = Path(path); temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    temp.replace(path)


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ceiling(value):
    return float(Decimal(str(value)).quantize(Decimal(".000001"), rounding=ROUND_CEILING))


def bound(stage):
    c = CAPS[stage]
    return (Decimal(c["input"]) + c["output"]) * RATE / 1000


def load_tasks():
    directory = ROOT / "data/node-tool-pilot-v1"
    tasks = json.loads((directory / "tasks.json").read_text())["tasks"]
    refs = json.loads((directory / "references.json").read_text())["tasks"]
    if len(tasks) != 3 or len({t["task_id"] for t in tasks}) != 3:
        raise ValueError("先导任务数量或身份改变")
    for t in tasks:
        if t["split"] != "development" or t["task_sha256"] != digest({k:v for k,v in t.items() if k != "task_sha256"}):
            raise ValueError("任务版本或开发标签不符")
        if refs[t["task_id"]]["task_sha256"] != t["task_sha256"]:
            raise ValueError("参考绑定错误")
    return tasks, refs


def model():
    from .ark_plan import catalog
    row = next(m for m in catalog()["models"] if m["model_id"] == "deepseek-v4-flash")
    return PilotModel("flash", "ark-plan", .05, .05, .55, billing_unit="AFP", api_model=row["model_id"],
        base_url="https://ark.cn-beijing.volces.com/api/plan/v3", api_key_env="CODEX_ARK_API_KEY",
        context_window=row["context_window_tokens"], max_output_tokens=MODEL_OUTPUT, wire_api="responses",
        json_mode_strategy="prompt-only", cached_input_cost_per_1k=.05)


def config(maximum, calls):
    m = model()
    raw = {"schemaVersion":"refractagent-planning-v2", "enabled":True,"defaultStrategy":"static",
        "maxProductionCostByUnit":{"AFP":maximum},"maxCalls":calls,"timeoutMs":600000,
        "models":[{"id":"flash","provider":"ark-node-study","model":m.api_model,
            "contextWindow":m.context_window,"maxOutputTokens":MODEL_OUTPUT,"inputPer1k":.05,
            "outputPer1k":.05,"cachedInputPer1k":.05,"billingUnit":"AFP",
            "deployment":"trusted-cloud","trustPolicy":"node-pilot"}],"roles":{"efficient":"flash"},
        "parameters":{"staticMode":"fixed"},"trustPolicies":[{"id":"node-pilot","residency":"CN",
            "auditLogging":True,"allowsSensitiveData":True}]}
    compile_config(raw)
    return raw


def implementation():
    paths = ["src/refractrouter/node_tool_study.py", "src/refractrouter/node_tools.py",
        "src/refractrouter/planning_runtime.py", "src/refractrouter/planning_budget.py",
        "src/refractrouter/planning_config.py", "src/refractrouter/task_budget.py",
        "src/refractrouter/task_execution.py", "src/refractrouter/compact_planning.py",
        "src/refractrouter/quality_runtime.py", "src/refractrouter/quality_study.py",
        "experiments/run_node_tool_study.py", "experiments/analyze_node_tool_study.py", "validation/dsh/plugin/scripts/run-node-tool-study.ts",
        "validation/dsh/plugin/src/planning-routing.ts", "validation/dsh/plugin/src/node-tools.ts",
        "validation/dsh/plugin/src/agent-provider.ts", "data/node-tool-pilot-v1/tasks.json",
        "data/node-tool-pilot-v1/references.json", "uv.lock", "validation/dsh/plugin/package-lock.json"]
    paths = sorted(set(paths) | {str(p.relative_to(ROOT)) for p in (ROOT/"src/refractrouter").rglob("*.py")}
        | {str(p.relative_to(ROOT)) for p in (ROOT/"src/refractrouter/resources").glob("*.json")}
        | {str(p.relative_to(ROOT)) for p in (ROOT/"validation/dsh/plugin/src").glob("*.ts")})
    return {name:file_hash(ROOT/name) for name in paths}


def case_spec(task, arm, repeat, prompt_id, *, phase="comparison", protocol_hash=""):
    payload = execution_payload(task)
    rid = f"{phase}-{task['task_id']}-{arm}-{prompt_id}-r{repeat}"
    system = PROMPTS[prompt_id] + (NODE_HINT if arm == "node-as-tool" else "")
    raw = {"runId":rid,"taskId":task["task_id"],"arm":arm,"repeat":repeat,"promptId":prompt_id,
        "phase":phase,"payload":payload,"system":system,"inputLimit":CAPS["main"]["input"],
        "maxMainCalls":4 if arm == "node-as-tool" else 1,"timeoutMs":600000,
        "provider":{"id":"ark-node-study","baseURL":model().base_url,"api":"openai-responses",
            "credentialRef":"CODEX_ARK_API_KEY","retryPolicy":{"mode":"normal","maxRetries":0}},
        "protocolSha256":protocol_hash,"dshVersion":"0.1.5-rc.3"}
    if arm == "node-as-tool":
        maximum = 4 * bound("main") + 3 * bound("expert")
        raw.update(maxModelCalls=7,nodeTools={"enabled":True,"maxNodeCalls":3,"maxInputChars":6000,
            "maxOutputTokens":CAPS["expert"]["output"]})
    elif arm == "dag":
        maximum = bound("planner") + 3 * bound("worker") + bound("final")
        raw["maxModelCalls"] = 5
    else:
        # Node JSON.stringify 的紧凑用户正文不大于这里带空格的 UTF-8 保守序列化。
        messages = [{"role":"system","content":system},{"id":rid,"role":"user","source":{"kind":"user"},
            "content":[{"type":"text","text":json.dumps(payload,ensure_ascii=False)}]}]
        maximum = (Decimal(request_input_bound(messages)) + CAPS["final"]["output"]) * RATE / 1000
        raw["maxModelCalls"] = 1
    raw["afpUpperBound"] = ceiling(maximum)
    raw["planningConfig"] = config(raw["afpUpperBound"],raw["maxModelCalls"])
    return raw


def prepare(prior_results=()):
    tasks, refs = load_tasks()
    optimization = [case_spec(t,"one-shot",rep,p,phase="prompt-audit")
        for rep in range(1,4) for t in tasks for p in (list(PROMPTS) if rep%2 else list(reversed(PROMPTS)))]
    schedule=[];rng=random.Random(2001029)
    for rep in range(1,4):
        for task in tasks:
            arms=list(ARMS);rng.shuffle(arms)
            for arm in arms:schedule.append({"taskId":task["task_id"],"arm":arm,"repeat":rep})
    # 提示赢家尚未知，按两个已冻结候选中更高的上界计算，不用测试结果缩小包络。
    comparison_bounds=[max(case_spec(t,s["arm"],s["repeat"],p)["afpUpperBound"] for p in PROMPTS)
        for s in schedule for t in tasks if t["task_id"]==s["taskId"]]
    total=ceiling(sum(Decimal(str(c["afpUpperBound"])) for c in optimization)+sum(Decimal(str(v)) for v in comparison_bounds))
    result={"schema":SCHEMA,"purpose":"一天内完成 node-as-tool 相对一次性回答与完整 DAG 的可复核开发先导",
        "tasks":{t["task_id"]:execution_payload(t) for t in tasks},"taskBindings":{t["task_id"]:t["task_sha256"] for t in tasks},
        "prompts":PROMPTS,"nodeHint":NODE_HINT,"caps":CAPS,"model":asdict(model()),
        "arms":list(ARMS),"repeats":3,"optimization":optimization,"schedule":schedule,
        "promptSelection":"关键事实检查通过数最多，其次失败检查最少，再以该候选总费用较低、提示 ID 字典序较小决胜；不使用随后三路线结果调参",
        "maxModelCalls":sum(c["maxModelCalls"] for c in optimization)+sum({"one-shot":1,"node-as-tool":7,"dag":5}[s["arm"]] for s in schedule),
        "conservativeAfpSum":total,"productionAfpUpperBound":APPROVED_AFP,
        "cumulativeModelCallLimit":APPROVED_CALLS,"priorResults":carry_in(prior_results),
        "admissionPolicy":"累计实际费用与未知预留不超过 286 AFP；每次派发按完整模型容量预留，已结算余额可复用；所有真实请求累计不超过 135 次","evaluationModelCalls":0,"httpRetries":0,"maxNodeFallbacks":0,
        "pricing":{"sourceUrl":"https://www.volcengine.com/docs/82379/2516283?lang=zh","verifiedAt":"2026-10-29",
            "inputCoefficient":.5,"outputCoefficient":.5,"discountAssumed":False,"unit":"AFP 套餐用量，非人民币实付"},
        "implementation":implementation(),"dshVersion":"0.1.5-rc.3","qualityVerdict":"Insufficient-evidence",
        "limits":"三类构造开发任务；不代表留出泛化或单模型池最优；确定性通过不代替真人语义双审。",
        "failurePolicy":"节点错误停止本任务下游并结算在途；未知用量、认证、账本或证据异常停止整批；无 HTTP 自动重试",
        "timing":"每任务从模型/规划执行开始计时，不含进程冷启动；另保留各调用时延及全过程外层耗时",
        "budgetIncludes":"18 次基线提示开发 + 27 次三路线样本；DAG 规划与专家费用均包含，不含未批准的额外付费评审"}
    result["protocolSha256"]=digest(result)
    return json.loads(json.dumps(result,ensure_ascii=False,allow_nan=False))


def validate(frozen):
    if frozen != prepare([ROOT/v["path"] for v in frozen.get("priorResults",[])]):
        raise ValueError("冻结任务、实现、模型、费用或提示发生变化；不得复用旧批准摘要")


class PilotBudget(TaskCallBudget):
    def __init__(self,client,maximum):
        super().__init__(client,maximum,1,max_calls=5,capture_payload=True)
        self.stages={};self.final_system=FINAL_SYSTEM
    def reserve(self,m,messages,*,label,**kwargs):
        stage=self.stages[label];cap=CAPS[stage];messages=deepcopy(messages)
        if stage=="final":messages[0]["content"]=self.final_system
        if request_input_bound(messages)>cap["input"]:raise ValueError("请求超过冻结阶段输入上限")
        r=super().reserve(replace(m,max_output_tokens=cap["output"]),messages,label=label,**kwargs)
        r.row.update(stage=stage,provider=m.provider,actual_model=m.api_model,billing_unit=m.billing_unit)
        return r


class RehearsalClient:
    max_retries=0
    def complete(self,m,messages,**kwargs):
        if messages[0]["content"]==COMPACT_PLANNER_SYSTEM:
            value={"reason":"离线调度演练，不是实际拆分决策","nodes":[
                {"id":"analyze","type":"synthesis","job":"分析资料，保留来源","parents":[],"difficulty":"medium","risk":"medium"},
                {"id":"check","type":"verification","job":"独立核对约束","parents":[],"difficulty":"medium","risk":"medium"},
                {"id":"answer","type":"generation","job":"完整交付","parents":["analyze","check"],"difficulty":"medium","risk":"medium"}]}
        elif messages[0]["content"] in PROMPTS.values():value={"answer":"离线交付，不构成质量证据","findings":[]}
        else:return ChatResponse("离线分析，来源 s1，未执行真实模型。",100,50,0,0,1,1,"stop",None)
        return ChatResponse(json.dumps(value,ensure_ascii=False),100,50,0,0,1,1,"stop",None)


def run_dag(case,out,*,simulated):
    out.mkdir(parents=True,exist_ok=False);started=time.monotonic()
    budget=PilotBudget(RehearsalClient() if simulated else OpenAICompatibleClient(max_retries=0,timeout_seconds=600),case["afpUpperBound"])
    budget.final_system=PROMPTS[case["promptId"]]
    lock=RLock()
    (out/"calls").mkdir()
    record={"runId":case["runId"],"status":"running","nodes":[],"simulated":simulated}
    def persist():
        with lock:
            record["costs"],record["calls"]=budget.snapshot();write(out/"dag.json",record)
    def archive(row,response):
        with lock:
            write(out/"calls"/(hashlib.sha256(row["label"].encode()).hexdigest()+".json"),asdict(response))
            persist()
    budget.on_reserve=lambda _:persist();budget.on_dispatch=lambda _:persist();budget.on_response=archive
    persist()
    try:
        budget.stages["planner"]="planner"
        response=budget.complete(model(),[{"role":"system","content":COMPACT_PLANNER_SYSTEM},
            {"role":"user","content":json.dumps({"task":case["payload"],"max_nodes":4},ensure_ascii=False)}],
            label="planner",timeout_seconds=600)
        plan=compile_compact(json.loads(response.content),criteria=case["payload"]["semantic_criteria"],max_nodes=4)
        record["plan"]=plan.to_dict()
        for n in plan.nodes:budget.stages["dag:"+n.node_id]="final" if n.node_id==plan.final_node_id else "worker"
        text=execute_nodes(plan,json.dumps(case["payload"],ensure_ascii=False),
            {n.node_id:"flash" for n in plan.nodes},{"flash":model()},budget,ExecutionPolicy(2,{"ark-plan":2},{"ark-plan":0}),
            record,persist,started=started,deadline=started+600,label_prefix="dag:",classify_failure=True)
        record.update(status="completed",output=text,taskElapsedMs=(time.monotonic()-started)*1000)
    except Exception as exc:record.update(status="failed",error=str(exc),failureKind="model-output" if isinstance(exc,ValueError) else "infrastructure")
    finally:budget.stop();persist()
    return record


def score_row(task,ref,text):
    try:
        parsed=parse_delivery(text);checks=check_output(task,ref,parsed)
        return {"factStatus":checks["status"],"qualityStatus":"fail" if checks["status"]=="fail" else "pending",
            "checks":checks["checks"],"unverified":checks["unverified"]}
    except (ValueError,KeyError,TypeError) as exc:
        return {"factStatus":"fail","qualityStatus":"fail","qualityError":str(exc),"checks":[]}


def run(frozen,out,*,node_modules,python,live=False,approved_hash=None,approved_afp=None):
    validate(frozen)
    if live and (approved_hash!=frozen["protocolSha256"] or approved_afp!=frozen["productionAfpUpperBound"]):
        raise ValueError("真实运行须匹配已批准的协议摘要和整个批次 AFP 上限")
    if live:
        import os
        if not os.environ.get("CODEX_ARK_API_KEY"):
            raise ValueError("缺少冻结模型凭证引用；尚未派发任何请求")
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False);(out/"cases").mkdir()
    tasks,refs=load_tasks();by_id={t["task_id"]:t for t in tasks}
    result={"schema":SCHEMA,"status":"running","simulated":not live,"protocolSha256":frozen["protocolSha256"],
        "runs":[],"realModelCalls":0,"actualOrReservedAfp":0,
        "cumulativeRealModelCalls":sum(v["realModelCalls"] for v in frozen["priorResults"]),
        "cumulativeActualOrReservedAfp":sum(v["actualOrReservedAfp"] for v in frozen["priorResults"]),"qualityVerdict":"Insufficient-evidence","providerBillingConfirmed":False}
    write(out/"frozen.json",frozen)
    def persist():write(out/"summary.json",result)
    def trial(case):
        if implementation()!=frozen["implementation"]:
            result["status"]="stopped-implementation-changed";persist();return False
        case["protocolSha256"]=frozen["protocolSha256"]
        refused=cumulative_admission(result,case)
        if refused:
            result["status"]=refused;persist();return False
        write(out/"cases"/(case["runId"]+".json"),case)
        directory=out/case["runId"];entered=time.monotonic()
        if case["arm"]=="dag":
            core=run_dag(case,directory,simulated=not live);calls=core["calls"]
            row={"status":core["status"],"output":core.get("output",""),"taskElapsedMs":core.get("taskElapsedMs"),
                "graphNodes":len(core.get("plan",{}).get("nodes",[])),"error":core.get("error"),"failureKind":core.get("failureKind")}
        else:
            command=["node",str(ROOT/"validation/dsh/plugin/scripts/run-node-tool-study.ts"),
                str(Path(node_modules).resolve()),str(Path(python).absolute()),str(out/"cases"/(case["runId"]+".json")),
                str(directory),"--execute-paid-run" if live else "--rehearse",frozen["protocolSha256"]]
            try:
                completed=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=case["timeoutMs"]/1000+30)
            except subprocess.TimeoutExpired as exc:
                def decoded(value):return value.decode(errors="replace") if isinstance(value,bytes) else value or ""
                completed=subprocess.CompletedProcess(command,124,decoded(exc.stdout),decoded(exc.stderr)+"宿主超过冻结时限，已终止；在途用量待核对")
            (out/(case["runId"]+".log")).write_text(completed.stdout+completed.stderr)
            records=list(directory.glob("evidence/planning/*.json"));calls=[];core_status=None
            if records:
                evidence=json.loads(records[0].read_text());calls=evidence["calls"];core_status=evidence["status"]
            row=json.loads((directory/"result.json").read_text()) if (directory/"result.json").exists() else {
                "status":"failed","output":"","error":str((directory/"failure.json").read_text()) if (directory/"failure.json").exists() else "宿主失败"}
            if completed.returncode != 0:
                row.update(status="failed",error=row.get("error") or completed.stderr[-2000:] or "宿主归档或执行异常")
            row["coreStatus"]=core_status
            if row["status"]!="completed":row["failureKind"]="model-output" if core_status in ("node-output-invalid","call-failed") else "infrastructure"
        row.update(runId=case["runId"],taskId=case["taskId"],arm=case["arm"],phase=case["phase"],
            repeat=case["repeat"],promptId=case["promptId"],calls=calls,outerElapsedMs=(time.monotonic()-entered)*1000,
            chargedOrReserved=sum(c["charged"] for c in calls),costKnown=all(c["status"] in ("billed","cancelled-before-dispatch") for c in calls))
        result["runs"].append(row)
        result["realModelCalls"]+=sum(c["status"]!="cancelled-before-dispatch" for c in calls) if live else 0
        result["actualOrReservedAfp"]+=row["chargedOrReserved"] if live else 0
        result["cumulativeRealModelCalls"]=result["realModelCalls"]+sum(v["realModelCalls"] for v in frozen["priorResults"])
        result["cumulativeActualOrReservedAfp"]=result["actualOrReservedAfp"]+sum(v["actualOrReservedAfp"] for v in frozen["priorResults"])
        row.update(score_row(by_id[case["taskId"]],refs[case["taskId"]],row.get("output","")) if row["status"]=="completed"
            else {"factStatus":"not-evaluated","qualityStatus":"pending","checks":[],"unverified":["未取得完整交付；运行错误不冒充模型事实错误"]})
        if (len(calls)>case["maxModelCalls"] or row["chargedOrReserved"]>case["afpUpperBound"]+1e-8
                or result["cumulativeActualOrReservedAfp"]>frozen["productionAfpUpperBound"]+1e-8
                or result["cumulativeRealModelCalls"]>frozen["cumulativeModelCallLimit"]):
            result["status"]="stopped-budget-integrity";persist();return False
        # 已结算的无效答案可以继续独立样本；传输、认证、未知用量或写入异常不能继续。
        if (not row["costKnown"] or not calls or row["status"]!="completed" and
                (row.get("failureKind")!="model-output" or any(c["status"]!="billed" for c in calls))):
            result["status"]="stopped-needs-inspection";persist();return False
        persist();return True
    persist()
    for case in frozen["optimization"]:
        if not trial(deepcopy(case)):return result
    ranking=[]
    for p in PROMPTS:
        rows=[r for r in result["runs"] if r["promptId"]==p]
        ranking.append((-sum(r["factStatus"]=="pass" for r in rows),
            sum(c["status"]=="fail" for r in rows for c in r["checks"]),sum(r["chargedOrReserved"] for r in rows),p))
    chosen=min(ranking)[-1];result["selectedPrompt"]=chosen
    result["promptSelectionEvidence"]=ranking;persist()
    for spec in frozen["schedule"]:
        case=case_spec(by_id[spec["taskId"]],spec["arm"],spec["repeat"],chosen)
        if not trial(case):return result
    result["status"]="completed-rehearsal" if not live else "completed-development-pilot"
    result["pairs"]=[]
    comparison=[r for r in result["runs"] if r["phase"]=="comparison"]
    for t in tasks:
        for rep in range(1,4):
            group={r["arm"]:r for r in comparison if r["taskId"]==t["task_id"] and r["repeat"]==rep}
            for arm in ("node-as-tool","dag"):
                a,b=group["one-shot"],group[arm]
                result["pairs"].append({"taskId":t["task_id"],"repeat":rep,"arm":arm,
                    "factTransition":a["factStatus"]+"→"+b["factStatus"],
                    "afpDifference":b["chargedOrReserved"]-a["chargedOrReserved"],
                    "elapsedDifferenceMs":(b.get("taskElapsedMs") or b["outerElapsedMs"])-(a.get("taskElapsedMs") or a["outerElapsedMs"]),
                    "semanticStatus":"pending"})
    persist();return result
