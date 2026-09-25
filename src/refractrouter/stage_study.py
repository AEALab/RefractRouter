"""Stage 三路线实验的冻结协议、零调用预检、工作区准备与结果汇总。"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import random
import statistics
import subprocess
import sys
import time

from .planning_policy import STAGE_RULE_VERSION


SCHEMA = "stage-routing-study-v1"
PILOT_MAX_AFP = 221.184
PILOT_PROMPT = """这是 Stage 路由的受控功能验收。禁止委派或启动子 Agent。严格按顺序执行，
每次模型回复最多发起一个工具调用，不得并行，也不得跳过已失败的步骤：
1. 使用 Bash 执行：python3 -c 'import sys; sys.exit(7)'
2. 工具返回后，在下一次续接中再次使用 Bash 执行完全相同的命令。
3. 第二次失败返回后，在下一次续接中使用 Bash 执行：pwd
4. pwd 返回后，在下一次续接中再次使用 Bash 执行：pwd
5. 第二次 pwd 返回后，不再调用工具，只输出 STAGE_PILOT_OK。
前两次非零退出是验收输入，不要修复文件、改写命令或提前结束。
"""

HIDDEN_CODE_CHECKS = {
    "code-defect-rounding": """from decimal import Decimal
from money import allocate
assert sum(allocate('0.05',[1,1,1])) == Decimal('0.05')
assert allocate('10.00',[]) == []
try: allocate('10.00',[1,-1])
except (ValueError, ZeroDivisionError): pass
else: raise AssertionError('negative weights accepted')
""",
    "code-defect-lru-zero": """from cache import LRUCache
c=LRUCache(0); c.put('a',1); assert c.get('a') is None
c=LRUCache(2); c.put('a',1); c.put('b',2); assert c.get('a')==1; c.put('c',3); assert c.get('b') is None
c.put('a',4); assert c.get('a')==4
""",
    "code-tdd-slug": """from slug import slugify
assert slugify('  Hello,  World! ') == 'hello-world'
assert slugify('Cafe\u0301 与 茶') == 'café-与-茶'
assert slugify('---') == ''
""",
    "code-tdd-ranges": """from ranges import merge_ranges
x=[(5,6),(1,2),(3,4),(9,10),(10,12)]; before=list(x)
assert merge_ranges(x)==[(1,6),(9,12)] and x==before
try: merge_ranges([(2,1)])
except ValueError: pass
else: raise AssertionError('invalid range accepted')
""",
    "code-multifile-inventory": """from repository import InventoryRepository
from service import reserve_many
r=InventoryRepository({'a':2,'b':1})
try: reserve_many(r,[('a',1),('b',2)])
except (ValueError, KeyError): pass
else: raise AssertionError('insufficient stock accepted')
assert r.stock=={'a':2,'b':1}
try: reserve_many(r,[('a',-1)])
except ValueError: pass
else: raise AssertionError('negative quantity accepted')
r=InventoryRepository({'a':3}); assert reserve_many(r,[('a',1),('a',2)]); assert r.stock['a']==0
""",
    "code-multifile-config": """import json, os, tempfile
from pathlib import Path
from loader import load_config
with tempfile.TemporaryDirectory() as d:
 p=Path(d)/'c.json'; p.write_text(json.dumps({'port':9000,'debug':False}))
 os.environ['APP_PORT']='9100'; os.environ['APP_DEBUG']='TrUe'
 try: c=load_config(p); assert c['port']==9100 and c['debug'] is True
 finally: os.environ.pop('APP_PORT'); os.environ.pop('APP_DEBUG')
 p.write_text(json.dumps({'unknown':1}))
 try: load_config(p)
 except ValueError: pass
 else: raise AssertionError('unknown key accepted')
""",
}


def canonical_digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def load_protocol(path):
    protocol = json.loads(Path(path).read_text())
    if protocol.get("schemaVersion") != SCHEMA:
        raise ValueError("未知 Stage 实验协议")
    tasks = protocol.get("tasks")
    if not isinstance(tasks, list) or len(tasks) != 12:
        raise ValueError("Stage 首轮实验必须冻结 12 个任务")
    ids = [task.get("id") for task in tasks]
    if any(not isinstance(task_id, str) or not task_id for task_id in ids) or len(set(ids)) != 12:
        raise ValueError("Stage 任务 ID 必须完整且唯一")
    families = [task.get("family") for task in tasks]
    if families.count("code") != 6 or families.count("research") != 6:
        raise ValueError("Stage 首轮实验必须包含 6 个代码任务和 6 个资料研究任务")
    categories = defaultdict(int)
    for task in tasks:
        categories[(task["family"], task.get("category"))] += 1
        if not isinstance(task.get("prompt"), str) or not task["prompt"].strip():
            raise ValueError(f"任务 {task['id']} 缺少提示")
        if task["family"] == "code" and not isinstance(task.get("files"), dict):
            raise ValueError(f"代码任务 {task['id']} 缺少初始文件")
        if task["family"] == "research" and not isinstance(task.get("sources"), dict):
            raise ValueError(f"研究任务 {task['id']} 缺少冻结资料")
    expected = {("code", "defect"): 2, ("code", "tdd"): 2, ("code", "multi-file"): 2,
                ("research", "fact-check"): 2, ("research", "comparison"): 2,
                ("research", "conflict"): 2}
    if dict(categories) != expected:
        raise ValueError("Stage 任务类别不是冻结的 2×6 构成")
    design = protocol.get("design", {})
    if design.get("arms") != ["static-flash", "static-pro", "stage"] or design.get("repeats") != 2:
        raise ValueError("Stage 实验必须使用三路线且每路线重复两次")
    limits = protocol.get("limits", {})
    if limits != {"maxCallsPerRun": 20, "timeoutMs": 900000,
                  "maxOutputTokensPerCall": 8192, "maxInputTokensPerCall": 65536}:
        raise ValueError("Stage 实验调用包络与冻结值不一致")
    return protocol


def schedule(protocol):
    rows = [{"runId": f"{task['id']}--{arm}--r{repeat}", "taskId": task["id"],
             "family": task["family"], "category": task["category"], "arm": arm, "repeat": repeat}
            for task in protocol["tasks"] for arm in protocol["design"]["arms"]
            for repeat in range(1, protocol["design"]["repeats"] + 1)]
    random.Random(protocol["design"]["orderSeed"]).shuffle(rows)
    for index, row in enumerate(rows, 1):
        row["order"] = index
    return rows


def _route_cost(model, limits):
    return ((limits["maxInputTokensPerCall"] / 1000) * model["inputPer1k"]
            + (limits["maxOutputTokensPerCall"] / 1000) * model["outputPer1k"])


def planning_config(protocol, arm):
    if arm not in protocol["design"]["arms"]:
        raise ValueError("未知实验路线")
    limits, models = protocol["limits"], protocol["models"]
    strategy = "stage" if arm == "stage" else "static"
    efficient = "flash" if arm != "static-pro" else "pro"
    maximum = (limits["maxCallsPerRun"] * _route_cost(models[efficient], limits)
               if strategy == "static" else _route_cost(models["flash"], limits)
               + (limits["maxCallsPerRun"] - 1) * _route_cost(models["pro"], limits))
    from .ark_plan import catalog
    ark_models = {row["model_id"]: row for row in catalog()["models"]}
    rows = []
    for key in ("flash", "pro"):
        source = models[key]
        metadata = ark_models.get(source["model"])
        if metadata is None:
            raise ValueError(f"冻结模型缺少 Ark 官方容量元数据：{source['model']}")
        row = {"id": key, "provider": source["provider"], "model": source["model"],
               # contextWindow 描述提供方真实容量；实验的输入与输出上限分别由
               # limits 和调用包络控制，不能把实验上限伪装成模型容量。DSH
               # 原生工具定义也属于请求输入，核心会用保守字节界限做准入。
               "contextWindow": metadata["context_window_tokens"],
               "maxOutputTokens": limits["maxOutputTokensPerCall"],
               "inputPer1k": source["inputPer1k"], "outputPer1k": source["outputPer1k"],
               "cachedInputPer1k": source["inputPer1k"], "billingUnit": "AFP",
               "deployment": "trusted-cloud", "trustPolicy": "ark-stage-study"}
        if protocol["design"]["reasoningEffort"] != "provider-default":
            row["reasoningEffort"] = protocol["design"]["reasoningEffort"]
        rows.append(row)
    return {"schemaVersion": "refractagent-planning-v2", "enabled": True,
            "defaultStrategy": strategy, "maxProductionCostByUnit": {"AFP": round(maximum, 6)},
            "timeoutMs": limits["timeoutMs"], "maxCalls": limits["maxCallsPerRun"],
            "models": rows, "roles": {"efficient": efficient, "capable": "pro"},
            "parameters": {**protocol["stageParameters"], "staticMode": "fixed"},
            "trustPolicies": [{"id": "ark-stage-study", "residency": "CN",
                               "auditLogging": True, "allowsSensitiveData": True}],
            "compatiblePairs": [["flash", "pro"], ["pro", "flash"]],
            "security": {"maxPromptBytes": 16 * 1024 * 1024}}


def render_dsh_patch(protocol, arm, runs_dir=".refractagent/runs"):
    """生成不含凭证的 headless profile 补丁；三个路线都走规划入口。"""
    config = planning_config(protocol, arm)
    provider = {"apiKeyEnv": "ARK_API_KEY", "api": "openai-responses",
                "baseURL": "https://ark.cn-beijing.volces.com/api/plan/v3",
                "retryPolicy": {"mode": "normal", "maxRetries": 0},
                "models": [{"id": row["model"], "name": row["model"],
                            "contextWindow": row["contextWindow"],
                            "maxTokens": row["maxOutputTokens"]} for row in config["models"]]}
    entries = [
        ("agent-default-model", {"provider": "refractagent", "model": "planning"}, False),
        ("settings", {"path": ".refractagent/settings.yaml", "watch": False}, False),
        ("llm-pi-ai", {"providers": {"ark": provider}}, False),
        ("refractagent", {"pythonExecutable": "refractagent", "runsDir": runs_dir,
                          "planningRouting": config}, False),
        ("tool-subagent-control", None, True), ("tool-subagent-list-agents", None, True),
        ("tool-subagent", None, True), ("tool-subagent-fork", None, True),
        ("tool-ralph", None, True),
    ]
    lines = []
    for plugin_id, value, disabled in entries:
        lines.append(f"- id: {plugin_id}")
        if disabled:
            lines.append("  disabled: true")
        else:
            lines.append("  config: " + json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    return "\n".join(lines) + "\n"


def preflight(protocol):
    rows = schedule(protocol)
    models = protocol["models"]
    limits = protocol["limits"]
    runs_per_arm = len(protocol["tasks"]) * protocol["design"]["repeats"]
    calls = limits["maxCallsPerRun"]
    research_runs = sum(row["family"] == "research" for row in rows)
    flash_calls = runs_per_arm * calls + runs_per_arm  # Stage 每任务首轮必为 Flash。
    pro_calls = runs_per_arm * calls + runs_per_arm * (calls - 1) + research_runs
    production = flash_calls * _route_cost(models["flash"], limits) + (
        pro_calls - research_runs) * _route_cost(models["pro"], limits)
    evaluation = research_runs * _route_cost(models["pro"], limits)
    task_hashes = {task["id"]: canonical_digest(task) for task in protocol["tasks"]}
    return {"schemaVersion": "stage-routing-preflight-v1",
            "protocolSha256": canonical_digest(protocol), "taskSha256": task_hashes,
            "stageRuleVersion": STAGE_RULE_VERSION,
            "runs": len(rows), "productionRuns": len(rows), "evaluationCalls": research_runs,
            "maxExecutionCalls": len(rows) * calls, "maxCallsIncludingEvaluation": len(rows) * calls + research_runs,
            "afpUpperBound": {"production": round(production, 6),
                              "evaluation": round(evaluation, 6),
                              "total": round(production + evaluation, 6)},
            "callUpperBoundByModel": {"deepseek-v4.1-flash": flash_calls,
                                      "deepseek-v4-pro": pro_calls},
            "limits": deepcopy(limits), "scheduleSha256": canonical_digest(rows),
            "dshPatchSha256": {arm: hashlib.sha256(render_dsh_patch(protocol, arm).encode()).hexdigest()
                               for arm in protocol["design"]["arms"]},
            "schedule": rows,
            "notes": [
                "上界按每次调用同时达到 65536 输入与 8192 输出 token 计算；实际结算通常更低。",
                "Stage 上界按首轮 Flash、其余 19 轮全部 Pro 计算。",
                "研究任务每次另计一次固定 Pro 盲评；功能验收调用不混入本实验。",
                "预检不发起模型调用；真实运行必须提供匹配的协议指纹和 AFP 双预算。",
            ]}


def pilot_preflight(protocol):
    """冻结真实小样本包络；不发起模型调用。"""
    pilot = deepcopy(protocol)
    pilot["limits"]["maxCallsPerRun"] = 6
    pilot["limits"]["timeoutMs"] = 300000
    config = planning_config(pilot, "stage")
    upper = config["maxProductionCostByUnit"]["AFP"]
    if upper != PILOT_MAX_AFP:
        raise ValueError("Stage 小样本 AFP 包络发生漂移")
    frozen = {"protocolSha256": canonical_digest(protocol), "prompt": PILOT_PROMPT,
              "strategy": "stage", "stageRuleVersion": STAGE_RULE_VERSION,
              "profile": "headless", "maxCalls": 6,
              "timeoutMs": 300000, "maxProductionAfp": upper,
              "evaluationAfp": 0, "httpRetries": 0,
              "patchSha256": hashlib.sha256(render_dsh_patch(pilot, "stage").encode()).hexdigest(),
              "expectedModels": ["deepseek-v4.1-flash", "deepseek-v4.1-flash",
                                 "deepseek-v4-pro", "deepseek-v4-pro",
                                 "deepseek-v4.1-flash"],
              "expectedReasons": ["no-signal", "ambiguous", "repeated-failure",
                                  "capable-hold", "ambiguous"]}
    return {**frozen, "pilotSha256": canonical_digest(frozen)}


def prepare_live_pilot(protocol, output_dir):
    """建立独立的 Stage 真实小样本目录，不读取或修改用户规划路由设置。"""
    output = Path(output_dir)
    if output.exists():
        raise ValueError("小样本输出目录已存在，拒绝覆盖或自动重跑")
    workspace = output / "workspace"
    workspace.mkdir(parents=True)
    settings = workspace / ".refractagent" / "settings.yaml"
    settings.parent.mkdir()
    settings.write_text("{}\n")
    pilot = deepcopy(protocol)
    pilot["limits"]["maxCallsPerRun"] = 6
    pilot["limits"]["timeoutMs"] = 300000
    (output / "pilot-preflight.json").write_text(
        json.dumps(pilot_preflight(protocol), ensure_ascii=False, indent=2) + "\n")
    (output / "stage-pilot.patch.yml").write_text(
        render_dsh_patch(pilot, "stage"))
    (workspace / "TASK.md").write_text(PILOT_PROMPT)
    return output


def run_live_pilot(protocol, output_dir, *, profile="headless"):
    """执行一次已授权小样本；无论成功或失败都不自动重发。"""
    output = Path(output_dir)
    preview = pilot_preflight(protocol)
    run_root = output / "workspace" / ".refractagent" / "runs"
    before = set(run_root.glob("planning/*.json")) if run_root.exists() else set()
    outcome, elapsed = _invoke_dsh(profile, output / "stage-pilot.patch.yml",
                                   output / "workspace", PILOT_PROMPT, 300000)
    (output / "dsh-stdout.txt").write_text(outcome.stdout or "")
    (output / "dsh-stderr.txt").write_text(outcome.stderr or "")
    record = _new_record(run_root, before)
    metrics = _metrics(record)
    reasons = [row.get("reason") for row in record.get("decisions", [])]
    checks = {
        "withinCallLimit": metrics["modelCalls"] <= preview["maxCalls"],
        "withinAfpLimit": metrics["productionAfp"] <= preview["maxProductionAfp"],
        "modelSequence": metrics["models"] == preview["expectedModels"],
        "decisionSequence": reasons == preview["expectedReasons"],
        "finalMarker": "STAGE_PILOT_OK" in (outcome.stdout or ""),
        "dshCompleted": outcome.returncode == 0 and record.get("status") == "completed",
    }
    summary = {"schemaVersion": "stage-routing-live-pilot-v1",
               "pilotSha256": preview["pilotSha256"], "profile": profile,
               "authorizedProductionAfp": PILOT_MAX_AFP, "evaluationAfp": 0,
               "elapsedMs": elapsed, "dshExitCode": outcome.returncode,
               **metrics, "decisionReasons": reasons, "checks": checks,
               "success": all(checks.values()), "automaticRetryCount": 0}
    (output / "pilot-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    return summary


def prepare(protocol, output_dir):
    output = Path(output_dir)
    if output.exists():
        raise ValueError("输出目录已存在；新问题必须使用新批次，不覆盖旧记录")
    output.mkdir(parents=True)
    task_by_id = {task["id"]: task for task in protocol["tasks"]}
    rows = schedule(protocol)
    for row in rows:
        task = task_by_id[row["taskId"]]
        workspace = output / "workspaces" / row["runId"]
        workspace.mkdir(parents=True)
        settings = workspace / ".refractagent" / "settings.yaml"
        settings.parent.mkdir()
        settings.write_text("{}\n")
        payload = task.get("files") if task["family"] == "code" else task.get("sources")
        for name, content in payload.items():
            relative = Path(name)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("任务文件路径越界")
            path = workspace / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        (workspace / "TASK.md").write_text(task["prompt"] + "\n")
    (output / "protocol.json").write_text(json.dumps(protocol, ensure_ascii=False, indent=2) + "\n")
    (output / "schedule.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    patches = output / "patches"
    patches.mkdir()
    for arm in protocol["design"]["arms"]:
        (patches / f"{arm}.yml").write_text(render_dsh_patch(protocol, arm))
    judge_protocol = deepcopy(protocol)
    judge_protocol["limits"]["maxCallsPerRun"] = 1
    (patches / "research-judge.yml").write_text(render_dsh_patch(
        judge_protocol, "static-pro"))
    return rows


def evaluate_code(task_id, workspace):
    script = HIDDEN_CODE_CHECKS.get(task_id)
    if script is None:
        raise ValueError("未知代码任务")
    outcome = subprocess.run([sys.executable, "-c", script], cwd=workspace,
                             text=True, capture_output=True, timeout=60)
    return {"success": outcome.returncode == 0, "exitCode": outcome.returncode,
            "stdout": outcome.stdout[-4000:], "stderr": outcome.stderr[-4000:]}


def evaluate_research(task, workspace):
    path = Path(workspace) / "answer.md"
    if not path.is_file():
        return {"success": False, "issues": ["missing-answer"]}
    text = path.read_text()
    acceptance = task["acceptance"]
    missing_citations = [source for source in acceptance["requiredCitations"]
                         if f"[{source}]" not in text]
    missing_facts = [fact for fact in acceptance["criticalFacts"] if fact not in text]
    fabricated = sorted(set(__import__("re").findall(r"\[([A-Z]\d+)\]", text))
                        - set(acceptance["requiredCitations"]))
    issues = ([f"missing-citation:{value}" for value in missing_citations]
              + [f"missing-critical-fact:{value}" for value in missing_facts]
              + [f"fabricated-citation:{value}" for value in fabricated])
    return {"success": not issues, "issues": issues,
            "deterministicScore": max(0, 100 - 10 * len(issues))}


def _new_record(root, before):
    paths = set(root.glob("planning/*.json")) if root.exists() else set()
    created = paths - before
    if len(created) != 1:
        raise RuntimeError("DSH 运行没有产生唯一的规划路由证据")
    return json.loads(created.pop().read_text())


def _metrics(record, *, capable_model="deepseek-v4-pro",
             efficient_model="deepseek-v4.1-flash"):
    calls = [call for call in record.get("calls", []) if call.get("purpose") not in ("compaction",)]
    if any(call.get("status") == "unknown-usage" for call in calls):
        raise RuntimeError("模型用量未知，停止整个实验批次")
    if any(call.get("status") != "billed" for call in calls):
        raise RuntimeError("模型调用没有完成结算，停止整个实验批次")
    models = [call.get("actual_model") for call in calls if call.get("purpose") in ("execute", "redo", "takeover")]
    costs = record.get("costsByUnit", {}).get("AFP", {})
    return {"modelCalls": len(models), "capableCalls": sum(model == capable_model for model in models),
            "modelSwitches": sum(left != right for left, right in zip(models, models[1:])),
            "recovered": any(models[index] == capable_model and efficient_model in models[index + 1:]
                             for index in range(len(models))),
            "firstByteMs": next((call.get("ttft_ms") for call in calls if call.get("ttft_ms") is not None), None),
            "productionAfp": float(costs.get("production", 0)), "models": models}


def _judge_payload(stdout):
    start, end = stdout.find("{"), stdout.rfind("}")
    if start < 0 or end < start:
        return {"score": None, "criticalFactError": None, "fabricatedCitation": None,
                "valid": False}
    try:
        value = json.loads(stdout[start:end + 1])
        score = value["score"]
        critical = value["criticalFactError"]
        fabricated = value["fabricatedCitation"]
        valid = type(score) in (int, float) and 0 <= score <= 100 and type(critical) is bool and type(fabricated) is bool
        return {"score": score if valid else None, "criticalFactError": critical if valid else None,
                "fabricatedCitation": fabricated if valid else None, "valid": valid}
    except (ValueError, KeyError, TypeError):
        return {"score": None, "criticalFactError": None, "fabricatedCitation": None,
                "valid": False}


def _invoke_dsh(profile, patch, workspace, prompt, timeout_ms):
    patch = Path(patch).resolve()
    workspace = Path(workspace).resolve()
    started = time.monotonic()
    try:
        outcome = subprocess.run(["dsh", "--profile", profile, "--patch", str(patch), prompt],
                                 cwd=workspace, text=True, capture_output=True,
                                 timeout=timeout_ms / 1000)
        return outcome, int((time.monotonic() - started) * 1000)
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(exc.cmd, 124, exc.stdout or "", exc.stderr or "dsh timeout"), timeout_ms


def run_paid_batch(protocol, output_dir, *, profile="headless"):
    """顺序执行已授权批次；所有路线复用 planning Static/Stage 以取得同构账本。"""
    if protocol["design"].get("reasoningEffort") not in {"high", "provider-default"}:
        raise ValueError("推理档位能力尚未冻结，拒绝启动付费批次")
    output = Path(output_dir)
    rows = json.loads((output / "schedule.json").read_text())
    records_path = output / "run-records.jsonl"
    existing = [] if not records_path.exists() else [json.loads(line) for line in records_path.read_text().splitlines() if line]
    completed = {row["runId"] for row in existing}
    task_by_id = {task["id"]: task for task in protocol["tasks"]}
    for row in rows:
        if row["runId"] in completed:
            continue
        task = task_by_id[row["taskId"]]
        workspace = output / "workspaces" / row["runId"]
        run_root = workspace / ".refractagent" / "runs"
        before = set(run_root.glob("planning/*.json")) if run_root.exists() else set()
        prompt = ("主实验禁止委派或启动子 Agent。严格遵守 TASK.md；研究任务禁止访问网络。\n\n"
                  + task["prompt"])
        outcome, elapsed = _invoke_dsh(profile, output / "patches" / f"{row['arm']}.yml",
                                       workspace, prompt, protocol["limits"]["timeoutMs"])
        record = _new_record(run_root, before)
        metrics = _metrics(record)
        if task["family"] == "code":
            evaluation = evaluate_code(task["id"], workspace)
            success = evaluation["success"]
            evaluation_afp = 0.0
            judge = None
        else:
            deterministic = evaluate_research(task, workspace)
            answer = (workspace / "answer.md").read_text() if (workspace / "answer.md").exists() else ""
            judge_workspace = output / "judge-workspaces" / row["runId"]
            judge_workspace.mkdir(parents=True, exist_ok=False)
            settings = judge_workspace / ".refractagent" / "settings.yaml"
            settings.parent.mkdir()
            settings.write_text("{}\n")
            (judge_workspace / "answer.md").write_text(answer)
            (judge_workspace / "rubric.json").write_text(json.dumps(protocol["evaluation"], ensure_ascii=False))
            judge_root = judge_workspace / ".refractagent" / "runs"
            judge_before = set(judge_root.glob("planning/*.json")) if judge_root.exists() else set()
            judge_prompt = ("只审核 answer.md，不使用工具、不修改文件。按 rubric.json 返回单个 JSON："
                            '{"score":0到100,"criticalFactError":true或false,'
                            '"fabricatedCitation":true或false,"reason":"简短依据"}。')
            judge_outcome, _ = _invoke_dsh(profile, output / "patches" / "research-judge.yml",
                                           judge_workspace, judge_prompt, protocol["limits"]["timeoutMs"])
            judge_record = _new_record(judge_root, judge_before)
            judge_metrics = _metrics(judge_record)
            judge = _judge_payload(judge_outcome.stdout)
            evaluation_afp = judge_metrics["productionAfp"]
            success = (deterministic["success"] and judge["valid"]
                       and judge["score"] >= protocol["evaluation"]["researchPass"]["minimumScore"]
                       and not judge["criticalFactError"] and not judge["fabricatedCitation"])
            evaluation = {"deterministic": deterministic, "judge": judge,
                          "judgeExitCode": judge_outcome.returncode}
        result = {**row, **metrics, "elapsedMs": elapsed, "success": success,
                  "evaluationAfp": evaluation_afp, "evaluation": evaluation,
                  "dshExitCode": outcome.returncode,
                  **({"failureReason": "timeout" if outcome.returncode == 124 else
                      "task-failed"} if not success else {})}
        with records_path.open("a") as stream:
            stream.write(json.dumps(result, ensure_ascii=False) + "\n")
            stream.flush()
            __import__("os").fsync(stream.fileno())
    records = [json.loads(line) for line in records_path.read_text().splitlines() if line]
    result = summarize(protocol, records)
    (output / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def summarize(protocol, records):
    expected = {row["runId"] for row in schedule(protocol)}
    actual = {row.get("runId") for row in records}
    if len(actual) != len(records) or not actual.issubset(expected):
        raise ValueError("运行记录包含重复或未知 runId")
    result = {"schemaVersion": "stage-routing-summary-v1", "complete": actual == expected,
              "expectedRuns": len(expected), "observedRuns": len(records), "arms": {}}
    for arm in protocol["design"]["arms"]:
        rows = [row for row in records if row["arm"] == arm]
        successes = sum(row.get("success") is True for row in rows)
        afp = sum(float(row.get("productionAfp", 0)) + float(row.get("evaluationAfp", 0)) for row in rows)
        first = [row["firstByteMs"] for row in rows if isinstance(row.get("firstByteMs"), (int, float))]
        elapsed = [row["elapsedMs"] for row in rows if isinstance(row.get("elapsedMs"), (int, float))]
        result["arms"][arm] = {"runs": len(rows), "successes": successes,
            "successRate": successes / len(rows) if rows else None,
            "totalAfp": afp, "afpPerSuccess": afp / successes if successes else None,
            "medianFirstByteMs": statistics.median(first) if first else None,
            "medianElapsedMs": statistics.median(elapsed) if elapsed else None,
            "switchRate": (sum(row.get("modelSwitches", 0) > 0 for row in rows) / len(rows)) if rows else None,
            "capableCallShare": (sum(row.get("capableCalls", 0) for row in rows)
                / max(1, sum(row.get("modelCalls", 0) for row in rows))),
            "recoveredRuns": sum(row.get("recovered") is True for row in rows),
            "failureReasons": dict(sorted({reason: sum(row.get("failureReason") == reason for row in rows)
                for reason in {row.get("failureReason") for row in rows if row.get("failureReason")}}.items()))}
    return result
