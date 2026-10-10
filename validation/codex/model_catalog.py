"""在客户端侧合成 Codex 目录；宿主指令只从用户指定的本机目录继承。"""
import argparse
from copy import deepcopy
import json
from pathlib import Path


def catalog(base, slug, advertised):
    matches = [m for m in base['models'] if m['slug'] == slug]
    if len(matches) != 1:
        raise ValueError('必须指定本机目录中唯一的宿主基线模型')
    result = []
    for route in advertised['data']:
        caps = route['refract']
        if caps['schemaVersion'] != 'refract-model-capabilities/1':
            raise ValueError('不支持的 Router 能力目录版本')
        model = deepcopy(matches[0])
        efforts = caps['acceptedReasoningEfforts']
        model.update(slug=route['id'], display_name=route['id'],
            description='独立模型路由；工具、权限及任务推进由 Codex 执行',
            default_reasoning_level=efforts[0] if efforts else None,
            supported_reasoning_levels=[{'effort':e,'description':'执行角色已冻结的推理等级'} for e in efforts],
            context_window=caps['contextWindow'], max_context_window=caps['contextWindow'],
            input_modalities=caps['inputModalities'], supports_image_detail_original=False,
            supports_reasoning_summaries=False, default_reasoning_summary='none',
            support_verbosity=False, supports_search_tool=False, use_responses_lite=False,
            apply_patch_tool_type=None, additional_speed_tiers=[], service_tiers=[],
            availability_nux=None, upgrade=None)
        # 目录继承的是宿主指令，不是基线模型的私有 custom 执行协议。
        # 目前 Router 只接通 function；让客户端保留原生 function 工具循环。
        model.update(tool_mode=None, experimental_supported_tools=[], node_repl_disabled=True)
        # 压缩由 Codex 执行；只根据真实容量收紧原客户端阈值。
        original = model.get('auto_compact_token_limit')
        limit = max(1, caps['contextWindow'] - caps['maxOutputTokens'])
        model['auto_compact_token_limit'] = min(original, limit) if original else limit
        result.append(model)
    ids = {m['slug'] for m in result}
    return {'models': [deepcopy(m) for m in base['models'] if m['slug'] not in ids] + result}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--baseline-model',required=True)
    p.add_argument('--gateway-models',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    value=catalog(json.loads(a.baseline.read_text()),a.baseline_model,json.loads(a.gateway_models.read_text()))
    # 文件含宿主指令，仅写本机；不覆盖日常目录。
    import os
    fd=os.open(a.output,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w') as f: json.dump(value,f,ensure_ascii=False,indent=2)


if __name__ == '__main__': main()
