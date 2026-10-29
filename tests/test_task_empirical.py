"""模拟完整核心轨迹，验证经验统计与影子选择；不宣称真实模型已取得资格。"""
from copy import deepcopy
from datetime import date, timedelta
import json

import pytest

from refractrouter.planning_config import compile_config
from refractrouter.planning_runtime import PlanningRuntime
from refractrouter.task_empirical import PROFILE, build_profile, make_context, predict
from refractrouter.task_outcomes import digest
from refractrouter.task_results import event
from tests.test_planning_routing import task_pool_configuration, begin, step, receipt
from experiments.build_task_empirical_profile import run as build_artifact


def configuration():
    cfg = task_pool_configuration()
    cfg.update(schemaVersion="refractagent-planning-v8", maxCalls=30)
    for model in cfg["models"]:
        model["revision"] = "fixture-r1"
        model["inputPer1k"] = .001 if model["id"] == "small" else .002
        model["outputPer1k"] = model["inputPer1k"] * 2
    profile = {"schemaVersion": PROFILE, "kind": "simulation", "observations": []}
    cfg["taskShadow"] = {"schemaVersion": "task-expected-cost-shadow-v1", "profile": profile,
        "profileSha256": digest(profile), "families": [{"id": "fixture-extract", "description": "闭合文本提取协议探针。",
        "criteriaSha256": digest("完整提取与引用合同"), "criterionIds": ["complete", "correct"]}],
        "routeVersion": "fixed-task-fixture-v1", "cacheCondition": "cold", "pricingDate": date.today().isoformat(),
        "expiresOn": (date.today() + timedelta(days=10)).isoformat(), "minSamples": 3, "qualityMin": .5}
    return cfg


def classifier(target=None, family="fixture-extract"):
    return json.dumps({"taskFamily": family, "answers": {"candidates": {
        key: {"score": .99 if target is None or key == target else .1, "missingInformation": 0.}
        for key in ("small", "large")}}})


def sample(directory, cfg, model, count=1, *, trailing_tool=False):
    runtime = PlanningRuntime(directory)
    run = begin(runtime, "task", config=cfg, session=directory.name)
    messages = [{"role": "user", "content": f"提取第{directory.name}份构造数据的字段。"}]
    execute = receipt(runtime, run, step(runtime, run, messages=messages), classifier(model))
    assert execute["model"]["id"] == model
    receipt(runtime, run, execute, content="模拟提取交付")
    for _ in range(count - 1):
        execute = step(runtime, run, messages=messages)
        assert execute["model"]["id"] == model
        receipt(runtime, run, execute, content="模拟提取交付")
    if trailing_tool:
        receipt(runtime, run, step(runtime, run, messages=messages), content="尚需读取工具结果",
                tools=({"id": "pending-tool", "name": "read", "arguments": "{}"},))
    runtime.handle({"op": "end", "runId": run})
    # 本例明确构造已知冷缓存观测；真实宿主缺缓存元数据时保持未知，不作同样处理。
    for row in runtime.runs[run]["budget"].records:
        row["cache_usage_available"] = True
        row["cache_usage_source"] = "fixture-cold-cache"
    runtime.persist(runtime.runs[run])
    result = runtime.handle({"op": "outcome", "runId": run, "identity": runtime.runs[run]["identity"]})
    last = result["candidates"][-2] if trailing_tool else result["candidates"][-1]
    assessment = {"schemaVersion": "whole-task-acceptance-v1", "candidateId": last["candidateId"],
        "candidateSha256": last["candidateSha256"], "criteriaSha256": cfg["taskShadow"]["families"][0]["criteriaSha256"],
        "method": "frozen-full-task-oracle-v1", "scope": "complete-delivery-and-requirements", "independent": True,
        "familyCorrect": True, "checks": [{"id": key, "passed": True} for key in ("complete", "correct")]}
    identity = runtime.runs[run]["identity"]
    scope = digest({k: identity[k] for k in ("session", "agent")})
    runtime.task_results.journal.append(scope, run, event("fixture-evaluation", "feedback",
        candidate=(last["candidateId"], last["candidateSha256"]), source="hidden-evaluation", actor="fixture-oracle",
        status="accepted", artifacts=[digest(assessment)], criteria=assessment["criteriaSha256"]))
    result = runtime.handle({"op": "outcome", "runId": run, "identity": identity})
    return {"result": result, "assessment": assessment, "sourceClusterId": str(directory.name), "split": "calibration"}


def profile_fixture(tmp_path):
    cfg = configuration()
    samples = [sample(tmp_path / f"{model}-{i}", cfg, model, 6 if model == "small" else 1)
               for model in ("small", "large") for i in range(3)]
    return cfg, samples, build_profile(samples, kind="simulation")


def query(cfg, profile, **updates):
    context = make_context(compile_config(cfg), "fixture-extract")
    args = {"candidate_ids": ["small", "large"], "fallback": "large",
            "bounds": {key: {"unit": "CNY", "amount": .01} for key in ("small", "large")},
            "remaining": {"CNY": 10}, "min_samples": 3, "quality_min": .5, "as_of": date.today().isoformat()}
    args.update(updates)
    return predict(profile, context, **args)


def test_cheap_per_call_but_repeated_full_task_cost_is_ranked_correctly(tmp_path):
    cfg, samples, profile = profile_fixture(tmp_path)
    result = query(cfg, profile)
    assert result["uncertain"] is False and result["candidateId"] == "large"
    rows = {r["modelId"]: r for r in result["rows"]}
    assert rows["small"]["estimate"]["mean"] > rows["large"]["estimate"]["mean"]
    assert rows["small"]["estimate"]["sampleCount"] == 3
    assert rows["small"]["estimate"]["rangeKind"] == "observed-not-guaranteed"
    assert result["productionQualificationClaimed"] is False
    assert result["corpusKind"] == "simulation"
    assert all(s["result"]["calls"][0]["purpose"] == "task" for s in samples)


def test_runtime_records_shadow_but_executes_legacy_choice_once_and_keeps_model(tmp_path):
    cfg, _, profile = profile_fixture(tmp_path)
    cfg["taskShadow"].update(profile=profile, profileSha256=digest(profile))
    runtime = PlanningRuntime(tmp_path / "runtime")
    run = begin(runtime, "task", config=cfg)
    judge = step(runtime, run)
    assert json.loads(judge["messages"][1]["content"])["contract"] == "task-decision-with-family-v3"
    assert "observations" not in judge["messages"][1]["content"]
    actual = receipt(runtime, run, judge, classifier())
    assert actual["model"]["id"] == "small"
    shadow = runtime.runs[run]["state"]["taskShadow"]
    assert shadow["candidateId"] == "large" and shadow["actualCandidateId"] == "small"
    assert shadow["uncertain"] is False
    assert shadow["actualSelectionChanged"] is False
    receipt(runtime, run, actual)
    continuation = step(runtime, run)
    assert continuation["purpose"] == "execute" and continuation["model"]["id"] == "small"
    assert sum(r["purpose"] == "task" for r in runtime.runs[run]["budget"].records) == 1


@pytest.mark.parametrize("change", ["model-revision", "price", "expired", "family-unknown", "cache-unknown"])
def test_drift_unknown_and_expiry_cannot_produce_a_certain_ranking(tmp_path, change):
    cfg, _, profile = profile_fixture(tmp_path)
    if change == "model-revision":
        cfg["models"][0]["revision"] = "fixture-r2"
    elif change == "price":
        cfg["models"][0]["inputPer1k"] *= 2
    elif change == "expired":
        cfg["taskShadow"]["pricingDate"] = "2020-01-01"
        cfg["taskShadow"]["expiresOn"] = "2020-01-02"
    elif change == "cache-unknown":
        cfg["taskShadow"]["cacheCondition"] = "unknown"
    else:
        cfg["taskShadow"]["families"][0]["id"] = "another-family"
    assert query(cfg, profile)["uncertain"] is True


def test_small_sample_quality_uncertainty_and_budget_are_not_replaced_by_suitability_score(tmp_path):
    cfg, _, profile = profile_fixture(tmp_path)
    assert query(cfg, profile, quality_min=.95)["uncertain"] is True
    result = query(cfg, profile, remaining={"CNY": .001})
    assert result["uncertain"] is True and result["candidateId"] is None
    assert query(cfg, profile, min_samples=4)["uncertain"] is True


def test_incomplete_or_misbound_assessment_does_not_inherit_user_or_model_approval(tmp_path):
    cfg, samples, _ = profile_fixture(tmp_path)
    for sample_row in samples:
        sample_row["assessment"]["scope"] = "selected-fact-fields"
    profile = build_profile(samples, kind="simulation")
    assert all(r["quality"] == "unknown" for r in profile["observations"])
    assert query(cfg, profile)["uncertain"] is True


def test_stale_profile_digest_and_legacy_config_do_not_silently_enable_shadow():
    cfg = configuration()
    cfg["taskShadow"]["profileSha256"] = "0" * 64
    with pytest.raises(ValueError, match="摘要不符"):
        compile_config(cfg)
    cfg = configuration()
    cfg["schemaVersion"] = "refractagent-planning-v7"
    for model in cfg["models"]:
        del model["revision"]
    with pytest.raises(ValueError, match="v8"):
        compile_config(cfg)


def test_frozen_builder_preserves_source_and_does_not_accept_holdout_or_duplicate_tasks(tmp_path):
    cfg, samples, _ = profile_fixture(tmp_path / "fixtures")
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source = source_dir / "samples.json"
    source.write_text(json.dumps({"schemaVersion": "task-calibration-input-v1", "kind": "simulation", "samples": samples}))
    before = source.read_bytes()
    result = build_artifact(source, tmp_path / "profile")
    assert result["observations"] == 6 and result["actualModelBenefitProven"] is False
    assert source.read_bytes() == before
    assert (tmp_path / "profile/inputs-before.json").read_bytes() == (tmp_path / "profile/inputs-after.json").read_bytes()
    with pytest.raises(FileExistsError):
        build_artifact(source, tmp_path / "profile")
    with pytest.raises(ValueError, match="分离"):
        build_artifact(source, source_dir / "profile")
    with pytest.raises(ValueError, match="重复"):
        build_profile([samples[0], samples[0]], kind="simulation")
    samples[0]["split"] = "holdout"
    with pytest.raises(ValueError, match="留出"):
        build_profile(samples, kind="simulation")


def test_public_feedback_or_unrecorded_assessment_cannot_make_quality_pass(tmp_path):
    cfg, samples, _ = profile_fixture(tmp_path)
    for value in samples:
        value["result"]["events"] = [r for r in value["result"]["events"] if r["event"]["source"] != "hidden-evaluation"]
    profile = build_profile(samples, kind="simulation")
    assert all(r["quality"] == "unknown" for r in profile["observations"])
    assert query(cfg, profile)["uncertain"] is True


def test_cross_unit_and_unknown_reserve_do_not_produce_certain_cost_order(tmp_path):
    cfg, _, profile = profile_fixture(tmp_path)
    mixed = deepcopy(profile)
    for row in mixed["observations"]:
        if row["modelId"] == "small":
            row["costObservation"]["costs"][0]["unit"] = "AFP"
    assert query(cfg, mixed)["reason"] == "incomparable-cost-dimensions"
    unknown = deepcopy(profile)
    for row in unknown["observations"]:
        row["costObservation"]["pricedCallAmountsComplete"] = False
        row["costObservation"]["costs"][0]["unknownProtected"] = "1"
    assert query(cfg, unknown)["uncertain"] is True


def test_repeated_sources_and_model_version_unknown_do_not_inflate_quality(tmp_path):
    cfg, _, profile = profile_fixture(tmp_path)
    repeated = deepcopy(profile)
    for row in repeated["observations"]:
        row["sourceClusterId"] = "same-source"
    assert query(cfg, repeated)["uncertain"] is True
    cfg["models"][0]["revision"] = "unknown"
    assert query(cfg, profile)["uncertain"] is True


def test_new_guidance_marks_prediction_stale_without_reclassifying_or_switching_model(tmp_path):
    cfg = configuration()
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "task", config=cfg)
    action = receipt(runtime, run, step(runtime, run), classifier())
    receipt(runtime, run, action)
    next_action = step(runtime, run, messages=[{"role": "user", "content": "另加一个新的验收要求。"}])
    assert next_action["model"]["id"] == action["model"]["id"]
    assert runtime.runs[run]["state"]["taskShadow"]["predictionStale"] is True
    assert sum(r["purpose"] == "task" for r in runtime.runs[run]["budget"].records) == 1


def test_changed_cache_condition_or_incomplete_cache_usage_keeps_profile_uncertain(tmp_path):
    cfg, samples, _ = profile_fixture(tmp_path)
    for value in samples:
        value["result"]["calls"][0]["cached_input_tokens"] = 10
    profile = build_profile(samples, kind="simulation")
    assert all(r["qualityReason"] == "cache-condition-mismatch" for r in profile["observations"])
    assert query(cfg, profile)["uncertain"] is True


def test_changed_normalized_exchange_or_price_data_invalidates_old_binding(tmp_path):
    from dataclasses import replace
    cfg, _, profile = profile_fixture(tmp_path)
    compiled = compile_config(cfg)
    old = compiled["models"]["small"]
    compiled["models"]["small"] = replace(old, input_cost_per_1k=old.input_cost_per_1k * 1.1)
    context = make_context(compiled, "fixture-extract")
    result = predict(profile, context, candidate_ids=["small", "large"], fallback="large",
        bounds={key: {"unit": "CNY", "amount": .01} for key in ("small", "large")}, remaining={"CNY": 10},
        min_samples=3, quality_min=.5, as_of=date.today().isoformat())
    assert result["uncertain"] is True


def test_earlier_stop_cannot_cover_later_accepted_tool_call(tmp_path):
    cfg = configuration()
    value = sample(tmp_path / "pending-final-tool", cfg, "small", trailing_tool=True)
    profile = build_profile([value], kind="simulation")
    assert profile["observations"][0]["quality"] == "unknown"
    assert profile["observations"][0]["qualityReason"] == "assessment-bound-to-earlier-delivery"


def test_budget_rejection_preserves_valid_quality_and_full_cost_predictions(tmp_path):
    cfg, _, profile = profile_fixture(tmp_path)
    result = query(cfg, profile, remaining={"CNY": .001})
    assert result["uncertain"] is True and result["candidateId"] is None
    assert result["costBasis"] == "empirical-full-managed-task"
    for row in result["rows"]:
        assert row["qualified"] is True and row["estimate"] is not None
        assert row["budgetAdmitted"] is False and row["selectionAdmitted"] is False


def test_unlimited_remaining_budget_uses_existing_ledger_semantics(tmp_path):
    cfg, _, profile = profile_fixture(tmp_path)
    assert query(cfg, profile, remaining={"CNY": float("inf")})["uncertain"] is False


@pytest.mark.parametrize("unlimited", ["cash", "reference"])
def test_runtime_unlimited_limits_do_not_turn_into_zero_shadow_balance(tmp_path, unlimited):
    cfg = configuration()
    if unlimited == "cash":
        cfg["maxProductionCostByUnit"]["CNY"] = 0
    else:
        cfg["maxReferenceCost"] = 0
    samples = [sample(tmp_path / f"{model}-{i}", cfg, model) for model in ("small", "large") for i in range(3)]
    profile = build_profile(samples, kind="simulation")
    cfg["taskShadow"].update(profile=profile, profileSha256=digest(profile))
    runtime = PlanningRuntime(tmp_path / "live-fixture")
    run = begin(runtime, "task", config=cfg)
    receipt(runtime, run, step(runtime, run), classifier())
    shadow = runtime.runs[run]["state"]["taskShadow"]
    assert shadow["uncertain"] is False
    assert all(r["budgetAdmitted"] for r in shadow["rows"])
