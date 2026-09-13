"""旧插件事件迁移保留原日志备份及所有消息，仅补可忽略标记。"""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

import pytest


def test_migration_is_backed_up_idempotent_and_preserves_other_events(tmp_path):
    if shutil.which('zstd') is None:
        pytest.skip('zstd CLI unavailable')
    spec=importlib.util.spec_from_file_location('migration',Path(__file__).parents[1]/'validation/dsh/mark_plugin_events_ignorable.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    rows=[{'type':'refractagent/tool-call','seq':1,'data':{'name':'fixture'}},
          {'type':'user/message','seq':2,'data':{'text':'保留'}},
          {'type':'unrelated/required','seq':3,'data':{}}]
    original=subprocess.run(['zstd','-q','-c'],input=('\n'.join(map(json.dumps,rows))+'\n').encode(),capture_output=True,check=True).stdout
    path=tmp_path/'session.jsonl.zstd';path.write_bytes(original)
    assert module.migrate(path)==1 and path.read_bytes()==original
    assert module.migrate(path,True)==1
    assert next(tmp_path.glob('*.before-ignorable-*')).read_bytes()==original
    first_frame=subprocess.run(['zstd','-q','-c'],input=(json.dumps({**rows[0],'ignorable':True},ensure_ascii=False,separators=(',',':'))+'\n').encode(),capture_output=True,check=True).stdout
    assert path.read_bytes().startswith(first_frame)
    decoded=[json.loads(line) for line in subprocess.run(['zstd','-dc',str(path)],capture_output=True,check=True).stdout.splitlines()]
    assert decoded==[{**rows[0],'ignorable':True},*rows[1:]]
    assert module.migrate(path,True)==0
