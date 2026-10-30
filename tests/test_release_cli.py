"""本机管理命令只操作版本材料；不加载模型凭据或派发请求。"""
from copy import deepcopy
import hashlib
import json

import pytest

from refractrouter.release_cli import main
from refractrouter.release_governance import core_identity,ReleaseStore
from tests.test_release_governance import release,evidence,expires


def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_freeze_initialize_register_trial_and_rollback_with_original_auth_preserved(tmp_path,capsys):
    old=release();config=deepcopy(old['configuration']);config['authTokenEnv']='TEST_ROUTER_TOKEN'
    cfg=tmp_path/'base.json';versions=tmp_path/'versions.json';snap=tmp_path/'snapshot.json'
    write(cfg,config);write(versions,old['versions'])
    assert main(['freeze','--config',str(cfg),'--versions',str(versions),'--name','测试基线','--output',str(snap)])==0
    report=json.loads(capsys.readouterr().out)
    assert not report['qualified'] and report['modelCalls']==0
    snapshot=json.loads(snap.read_bytes())
    assert snapshot['implementationSha256']==core_identity()
    registry=tmp_path/'registry';gateway=tmp_path/'governed.json'
    assert main(['init','--registry',str(registry),'--snapshot',str(snap),'--snapshot-sha256',report['fileSha256'],
        '--actor','测试维护者','--gateway-config-output',str(gateway)])==0
    assert json.loads(gateway.read_bytes())['authTokenEnv']=='TEST_ROUTER_TOKEN'
    capsys.readouterr()
    # 构造通过证据只测试命令流，不声称已有真实发布资格。
    new=deepcopy(config);new['providers']['fake']['baseURL']='http://127.0.0.1:1/new'
    write(cfg,new)
    target=tmp_path/'target.json'
    main(['freeze','--config',str(cfg),'--versions',str(versions),'--name','构造试用版本','--output',str(target)])
    target_report=json.loads(capsys.readouterr().out);target_snapshot=json.loads(target.read_bytes())
    proof=tmp_path/'evidence.json';proof_sha=write(proof,evidence(target_snapshot))
    assert main(['register','--registry',str(registry),'--snapshot',str(target),'--snapshot-sha256',target_report['fileSha256'],
        '--evidence',str(proof),'--evidence-sha256',proof_sha,'--actor','测试维护者'])==0
    assert json.loads(capsys.readouterr().out)['qualified']
    assert main(['trial','--registry',str(registry),'--release',target_report['releaseSha256'],'--max-tasks','2',
        '--expires',expires(),'--actor','测试维护者','--explicit-trial'])==0
    assert json.loads(capsys.readouterr().out)['maxNewTasks']==2
    assert main(['rollback','--registry',str(registry),'--actor','测试维护者','--reason','结束构造试用'])==0
    rolled=json.loads(capsys.readouterr().out)
    assert rolled['newTasksOnly'] and not rolled['unknownUsageReleased']
    assert main(['history','--registry',str(registry)])==0
    assert len(json.loads(capsys.readouterr().out)['versions'])==2


def test_digest_mismatch_and_existing_output_cannot_initialize(tmp_path):
    p=tmp_path/'snapshot.json';write(p,release())
    with pytest.raises(ValueError,match='摘要不符'):
        main(['init','--registry',str(tmp_path/'registry'),'--snapshot',str(p),'--snapshot-sha256','0'*64,
            '--actor','测试维护者','--gateway-config-output',str(tmp_path/'new.json')])
    assert not (tmp_path/'registry').exists()


def test_new_publication_after_manual_revalidation_has_distinct_identity_without_changing_context():
    from refractrouter.release_governance import frozen_release
    first=release()
    second=frozen_release(first['configuration'],first['versions'],implementation=first['implementationSha256'],
        publication_id='人工核对后的新版本')
    assert first['releaseSha256']!=second['releaseSha256']
    assert first['contextSha256']==second['contextSha256']
