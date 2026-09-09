"""本地确定性核验材料中的可执行事实；不联网、不调用模型、不代替人工规划复核。"""
from itertools import groupby
import json
from pathlib import Path
import sqlite3


def audit():
    with sqlite3.connect(':memory:') as connection:
        connection.execute('PRAGMA foreign_keys=OFF')
        connection.execute('BEGIN')
        connection.execute('PRAGMA foreign_keys=ON')
        within = connection.execute('PRAGMA foreign_keys').fetchone()[0]
        connection.rollback()
        connection.execute('PRAGMA foreign_keys=ON')
        outside = connection.execute('PRAGMA foreign_keys').fetchone()[0]
        connection.execute('CREATE TABLE parent(id INTEGER PRIMARY KEY)')
        connection.execute('CREATE TABLE child(id INTEGER REFERENCES parent(id) DEFERRABLE INITIALLY DEFERRED)')
        connection.execute('INSERT INTO child VALUES(7)')
        failed_commit = False
        try:
            connection.commit()
        except sqlite3.IntegrityError:
            failed_commit = True
        connection.execute('INSERT INTO parent VALUES(7)')
        connection.commit()
        with sqlite3.connect(':memory:') as other:
            other.execute('PRAGMA foreign_keys=OFF')
            separate = other.execute('PRAGMA foreign_keys').fetchone()[0]
    assert (within, outside, separate, failed_commit) == (0, 1, 0, True)
    values = [('A', 2), ('B', 5), ('A', 3), ('B', 7)]
    saved = list(groupby(values, key=lambda row: row[0]))
    delayed = [(key, list(group)) for key, group in saved]
    fixed = [(key, sum(row[1] for row in group)) for key, group in
             groupby(sorted(values, key=lambda row: row[0]), key=lambda row: row[0])]
    assert [key for key, _ in delayed] == ['A', 'B', 'A', 'B']
    assert all(not group for _, group in delayed)
    assert fixed == [('A', 5), ('B', 12)]
    return {'model_calls': 0, 'sqlite_version': sqlite3.sqlite_version,
        'sqlite': {'inside_transaction_enabled': within, 'outside_transaction_enabled': outside,
                   'second_connection_enabled': separate, 'unresolved_deferred_commit_failed': failed_commit,
                   'resolved_deferred_commit_passed': True},
        'groupby': {'delayed_groups': delayed, 'corrected_totals': fixed},
        'wai': '规范事实经官方页面核对；本文未执行屏幕阅读器或人工无障碍验收。',
        'human_review': False}


if __name__ == '__main__':
    result = audit()
    output = Path(__file__).with_name('material-audit.json')
    if output.exists():
        raise SystemExit('保留既有审查证据；重跑请使用新的输出位置')
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))
