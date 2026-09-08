"""失败轮次不可将未完成测试当成零分或成功；原始证据必须先核对。"""
from pathlib import Path
import json,hashlib

import pytest

from experiments.summarize_dag_study import summarize_study

ROOT=Path(__file__).resolve().parents[1]
FAILED=ROOT/'reports/dag-decomposition/issue-32-subscription-20260907/study-v2'


def test_real_early_failure_has_no_fake_scores_or_comparison():
    text=summarize_study(FAILED)
    assert '已取得评分的测试运行 0/54' in text
    assert '不可用' in text and '配对证据不足' in text
    assert '5.01975000' in text and '15.04300000' in text
    assert '达到探索性门槛' not in text


def test_changed_archive_cannot_generate_a_report(tmp_path):
    (tmp_path/'study-result.json').write_text('{}')
    (tmp_path/'artifact-index.json').write_text(json.dumps({'study-result.json':hashlib.sha256(b'original').hexdigest()}))
    with pytest.raises(ValueError,match='index mismatch'):
        summarize_study(tmp_path)


def test_partial_holdout_reports_observed_tasks_and_failed_attempt():
    text = summarize_study(FAILED.parent/'study-v3')
    assert '已评分的独立测试任务 1/3 个' in text
    assert '已保存结果的测试运行 17 次，其中执行失败 1 次' in text
    assert '| dag-node-a | 2/9 | 1 | 2 | 0 |' in text
    assert '配对证据不足' in text
