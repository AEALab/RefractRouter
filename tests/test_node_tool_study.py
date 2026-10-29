"""先导协议的容量、真实执行绑定与事实参考；无付费模型调用。"""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import pytest

from refractrouter.node_tool_study import (ROOT,ARMS,PROMPTS,CAPS,prepare,validate,load_tasks,
    case_spec,run_dag,run,score_row)
from refractrouter.planning_runtime import PlanningRuntime
from refractrouter.task_budget import request_input_bound
from tests.test_planning_routing import configuration


def test_preregistered_three_arm_scope_and_full_budget():
    f=prepare()
    assert len(f["optimization"])==18 and len(f["schedule"])==27
    assert f["maxModelCalls"]==135
    assert f["httpRetries"]==0 and f["evaluationModelCalls"]==0
    assert set(f["arms"])==set(ARMS)
    assert f["conservativeAfpSum"]<=f["productionAfpUpperBound"]
    assert f["productionAfpUpperBound"]==286
    assert all(set(v)=={"instruction","materials","requested_findings","semantic_criteria","output_contract"} for v in f["tasks"].values())
    assert all("expected" not in json.dumps(c["payload"]) for c in f["optimization"])
    validate(f)
    validate(json.loads(json.dumps(f)))


def test_approval_cannot_change_prompts_or_task_material(tmp_path):
    f=prepare();f["tasks"]["procurement-versions"]["instruction"]+="篡改"
    with pytest.raises(ValueError,match="冻结"):
        run(f,tmp_path/"run",node_modules="/missing",python="/missing",live=True,
            approved_hash=f["protocolSha256"],approved_afp=f["productionAfpUpperBound"])
    assert not (tmp_path/"run").exists()


def test_live_requires_exact_approval_before_any_process(tmp_path):
    f=prepare()
    with pytest.raises(ValueError,match="批准"):
        run(f,tmp_path/"run",node_modules="/missing",python="/missing",live=True)
    assert not (tmp_path/"run").exists()


def test_dag_rehearsal_uses_existing_nodes_with_planner_in_ledger(tmp_path):
    t=load_tasks()[0][0]
    c=case_spec(t,"dag",1,"existing-contract")
    result=run_dag(c,tmp_path/"dag",simulated=True)
    assert result["status"]=="completed"
    assert len(result["plan"]["nodes"])==3
    assert len(result["calls"])==4
    assert {r["stage"] for r in result["calls"]}=={"planner","worker","final"}
    assert all(r["status"]=="billed" for r in result["calls"])
    assert len(list((tmp_path/"dag/calls").glob("*.json")))==4
    assert result["execution"]["peak_active_nodes"]>=1
    assert result["costs"]["production"]<=c["afpUpperBound"]


def test_ordered_reference_vectors_are_not_sets():
    tasks,refs=load_tasks()
    for tid,key in [("ledger-idempotency","remaining"),("release-dependencies","critical_path")]:
        t=next(t for t in tasks if t["task_id"]==tid)
        values={c["field"]:c["expected"] for c in refs[tid]["checks"]}
        values[key]=list(reversed(values[key]))
        out={"answer":"参考测试，不是语义通过","findings":[{"id":k,"value":v,
            "sources":[s["source_id"] for s in t["materials"]]} for k,v in values.items()]}
        assert score_row(t,refs[tid],json.dumps(out))["factStatus"]=="fail"


def test_reference_arithmetic_independently_recomputed():
    _,refs=load_tasks()
    p={c["field"]:c["expected"] for c in refs["procurement-versions"]["checks"]}
    assert Decimal(240)*58*Decimal("1.13")+600==Decimal(str(p["cost_a"]))
    assert Decimal(240)*65*Decimal(".96")+800==p["cost_b"]
    assert 240*62+680==p["cost_c"]
    assert 240*59+900==p["cost_d"]
    # 按事件身份及载荷重放，和冻结参考字段独立核对。
    events=[("p1","O1","pay",100,"success"),("p1","O1","pay",100,"success"),
        ("r1","O1","refund",30,"success"),("r2","O1","refund",20,"success"),
        ("r2","O1","refund",20,"success"),("p2","O2","pay",80,"success"),
        ("r3","O2","refund",90,"success"),("p3","O3","pay",120,"success"),
        ("r4","O3","refund",120,"success"),("r4","O2","refund",120,"success"),
        ("r5","O1","refund",60,"success"),("p4","O2","pay",60,"pending"),("p5","O4","pay",50,"success")]
    seen={};balances={};paid=refunded=duplicates=conflicts=rejected=pending=0
    for eid,oid,kind,amount,status in events:
        payload=(oid,kind,amount,status)
        if eid in seen:
            if seen[eid]==payload:duplicates+=1
            else:conflicts+=1
            continue
        seen[eid]=payload
        if status!="success":pending+=amount;continue
        if kind=="refund" and amount>balances.get(oid,0):rejected+=1;continue
        balances[oid]=balances.get(oid,0)+(amount if kind=="pay" else -amount)
        if kind=="pay":paid+=amount
        else:refunded+=amount
    actual={"total_paid":paid,"total_refunded":refunded,"net":paid-refunded,
        "remaining":[balances[k] for k in ("O1","O2","O3","O4")],"duplicate_count":duplicates,
        "conflict_count":conflicts,"rejected_refunds":rejected,"pending_excluded":pending,"wrong_key":"order_id"}
    assert actual=={c["field"]:c["expected"] for c in refs["ledger-idempotency"]["checks"]}


def test_core_enforces_input_limit_before_reservation(tmp_path):
    r=PlanningRuntime(tmp_path)
    cfg=configuration("static")
    req={"op":"begin","identity":{"session":"s","agent":"a","turn":1},"config":cfg,"callInputLimit":512}
    run_id=r.handle(req)["runId"]
    with pytest.raises(ValueError,match="输入超过"):
        r.handle({"op":"step","runId":run_id,"messages":[{"role":"user","content":"原始材料"*200}],"tools":[]})
    assert r.runs[run_id]["budget"].records==[]
    with pytest.raises(ValueError,match="已经冻结"):
        r.handle({**req,"callInputLimit":1024})


def test_false_facts_cannot_become_pending():
    tasks,refs=load_tasks();t=tasks[0]
    output={"answer":"没有独立语义审查","findings":[]}
    s=score_row(t,refs[t["task_id"]],json.dumps(output))
    assert s["factStatus"]==s["qualityStatus"]=="fail"
