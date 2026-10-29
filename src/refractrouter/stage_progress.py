"""按检查器和断言身份比较进展；只产生影子建议，不执行工具、Judge 或模型。"""
from copy import deepcopy
import re

from .host_evidence import validate_evidence
from .purpose_review import digest, wire

VERSION = "stage-progress-shadow-v1"
CHECK_VERSION = "stage-check-evidence-v1"


def _id(value):
    return isinstance(value, str) and bool(value) and value == value.strip() and len(value) <= 256


def _sha(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def compile_shadow(raw):
    if raw is None:
        return None
    wire(raw)
    if not isinstance(raw, dict) or set(raw) != {"schemaVersion", "checkers", "holdTurns", "stallConfirmations"}:
        raise ValueError("Stage 影子配置字段无效")
    if raw["schemaVersion"] != VERSION:
        raise ValueError("未知 Stage 影子版本")
    for key, minimum in (("holdTurns", 1), ("stallConfirmations", 2)):
        if type(raw[key]) is not int or not minimum <= raw[key] <= 100:
            raise ValueError("Stage 影子保持/失败确认次数无效")
    if not isinstance(raw["checkers"], list) or not 1 <= len(raw["checkers"]) <= 32:
        raise ValueError("Stage 影子须冻结检查器")
    seen = set()
    for checker in raw["checkers"]:
        if not isinstance(checker, dict) or set(checker) != {"id", "revision", "suiteSha256", "assertionIds"}:
            raise ValueError("Stage 检查器字段无效")
        if not _id(checker["id"]) or checker["id"] in seen or not _id(checker["revision"]) or not _sha(checker["suiteSha256"]):
            raise ValueError("Stage 检查器身份或版本无效")
        seen.add(checker["id"])
        ids = checker["assertionIds"]
        if (not isinstance(ids, list) or not 1 <= len(ids) <= 256
                or any(not _id(key) for key in ids) or len(set(ids)) != len(ids)):
            raise ValueError("Stage 检查器必须冻结不重复的完整断言集合")
    return deepcopy(raw)


def initial_state(task_sha256):
    if not _sha(task_sha256):
        raise ValueError("Stage 影子须绑定任务摘要")
    return {"taskSha256": task_sha256, "role": "efficient", "hold": 0,
            "seen": {}, "checks": {}, "unresolved": {}, "relapse": {}, "snapshot": None,
            "generation": -1, "minimumGeneration": 0}


def _packet(event, config, task_sha256):
    value = event.get("validation")
    if not isinstance(value, dict) or set(value) != {
        "schemaVersion", "taskSha256", "checkerId", "checkerRevision", "suiteSha256",
        "snapshotSha256", "codeGeneration", "phase", "complete", "checks"
    }:
        return None
    checker = next((c for c in config["checkers"] if c["id"] == value["checkerId"]), None)
    if (checker is None or value["schemaVersion"] != CHECK_VERSION or value["taskSha256"] != task_sha256
            or value["checkerRevision"] != checker["revision"] or value["suiteSha256"] != checker["suiteSha256"]
            or not _sha(value["snapshotSha256"]) or value["phase"] not in ("expected-red", "acceptance")
            or type(value["codeGeneration"]) is not int or not 0 <= value["codeGeneration"] <= 2**53 - 1
            or value["complete"] is not True or not isinstance(value["checks"], list)):
        return None
    checks = value["checks"]
    if (any(not isinstance(c, dict) or set(c) != {"id", "status"} or not _id(c["id"])
            or c["status"] not in ("passed", "failed", "unknown") for c in checks)
            or len({c["id"] for c in checks}) != len(checks)
            or {c["id"] for c in checks} != set(checker["assertionIds"])):
        return None
    return value


def decide(events, state, config, task_sha256):
    """状态仅在宿主真正派发下一次调用后提交；正文不能填补结构化断言。"""
    config = compile_shadow(config)
    if config is None or not _sha(task_sha256):
        raise ValueError("Stage 影子缺少配置或任务身份")
    wire(events)
    events = validate_evidence(events)
    proposed = deepcopy(state) if state is not None else initial_state(task_sha256)
    changed_task = proposed["taskSha256"] != task_sha256
    if changed_task:
        proposed = initial_state(task_sha256)
    config_sha = digest(config)
    if proposed.get("configSha256", config_sha) != config_sha:
        raise ValueError("Stage 影子检查器或规则版本漂移")
    proposed["configSha256"] = config_sha
    fresh = []
    for event in events:
        previous = proposed["seen"].get(event["id"])
        identity = digest(event)
        if previous is not None and previous != identity:
            raise ValueError("Stage 影子同一工具身份出现矛盾证据")
        if previous is None:
            fresh.append(event)
            proposed["seen"][event["id"]] = identity
    if len(proposed["seen"]) > 10000:
        raise ValueError("Stage 影子证据超过容量，不能丢弃去重历史后继续")
    before, hold_before = proposed["role"], proposed["hold"]
    upgrade_keys, recovered, blocked = set(), False, False
    signals = ["task-context-reset"] if changed_task else []
    for event in fresh:
        if event["status"] not in ("completed", "failed"):
            signals.append("environment-or-unknown")
            blocked = True
            continue
        if event["kind"] == "mutate":
            # 写入成功不是验收进展，且会使之前快照上的通过过时。
            proposed["snapshot"] = None
            proposed["minimumGeneration"] = max(proposed["minimumGeneration"], proposed["generation"]) + 1
            upgrade_keys.clear()
        value = _packet(event, config, task_sha256)
        if value is None:
            signals.append("unverified-or-incomparable")
            blocked = blocked or event["status"] == "failed" or "validation" in event
            continue
        generation, snapshot = value["codeGeneration"], value["snapshotSha256"]
        if generation < max(proposed["minimumGeneration"], proposed["generation"]):
            signals.append("stale-code-generation")
            continue
        if generation == proposed["generation"] and snapshot != proposed["snapshot"]:
            signals.append("contradictory-snapshot-generation")
            blocked = True
            continue
        if generation > proposed["generation"]:
            proposed.update(generation=generation, snapshot=snapshot)
            upgrade_keys.clear()
        if value["phase"] == "expected-red":
            signals.append("normal-red-test")
            blocked = True
            continue
        if any(c["status"] == "unknown" for c in value["checks"]):
            signals.append("acceptance-unknown")
            blocked = True
            continue
        key = value["checkerId"]
        failed = sorted(c["id"] for c in value["checks"] if c["status"] == "failed")
        if not failed and event["status"] == "failed":
            signals.append("contradictory-host-failure")
            blocked = True
            continue
        previous = proposed["checks"].get(key)
        streak = 1
        upgrade_keys.discard(key)
        if failed:
            if previous and previous["failed"]:
                old, new = set(previous["failed"]), set(failed)
                if old == new:
                    streak = previous["streak"] + 1
                    signals.append("same-assertions-no-progress")
                    if streak >= config["stallConfirmations"]:
                        upgrade_keys.add(key)
                elif new < old:
                    signals.append("failure-set-shrunk")
                else:
                    signals.append("different-failures-unknown")
            else:
                signals.append("first-reasonable-failure")
            if before == "efficient" and set(failed) & set(proposed["relapse"].get(key, [])):
                upgrade_keys.add(key)
                signals.append("failure-after-restore")
            proposed["unresolved"][key] = {"snapshot": snapshot, "generation": generation}
        else:
            signals.append("full-checker-pass")
            recovered = True
        proposed["checks"][key] = {"snapshot": snapshot, "generation": generation, "failed": failed, "streak": streak}
        proposed["snapshot"] = snapshot
    all_pass = bool(proposed["unresolved"]) and all(
        checker["id"] in proposed["checks"]
        and not proposed["checks"][checker["id"]]["failed"]
        and proposed["checks"][checker["id"]]["snapshot"] == proposed["snapshot"]
        and proposed["checks"][checker["id"]]["generation"] == proposed["generation"]
        for checker in config["checkers"])
    changed_snapshot = all(row["snapshot"] != proposed["snapshot"] and row["generation"] < proposed["generation"]
                           for row in proposed["unresolved"].values())
    if recovered and all_pass and changed_snapshot and not blocked:
        # 同一新边界中更早的失败已被当前完整验收解决，不能只看历史中途状态。
        upgrade_keys.clear()
    if upgrade_keys:
        proposed.update(role="capable", hold=config["holdTurns"] - 1)
        for key, row in proposed["checks"].items():
            if key in upgrade_keys:
                proposed["relapse"][key] = sorted(set(proposed["relapse"].get(key, [])) | set(row["failed"]))
        reason = "assertion-stall-upgrade"
    elif before == "capable":
        proposed["hold"] = max(0, hold_before - 1)
        if hold_before == 0 and recovered and all_pass and changed_snapshot and not blocked:
            proposed.update(role="efficient", hold=0, unresolved={})
            reason = "new-snapshot-full-acceptance-restore"
        else:
            reason = "capable-hold" if hold_before > 0 else "no-new-acceptance-keep-capable"
    else:
        reason = "efficient-without-confirmed-stall"
    return proposed, {"schemaVersion": VERSION, "mode": "shadow", "role": proposed["role"],
        "reason": reason, "progress": signals or ["no-new-evidence"], "evidenceIds": [e["id"] for e in fresh],
        "holdBefore": hold_before, "holdAfter": proposed["hold"], "taskSha256": task_sha256,
        "actualSelectionChanged": False, "wholeTaskQualityProven": False,
        "scope": "configured-host-checkers-only"}
