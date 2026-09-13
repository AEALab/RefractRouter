"""按公开合同解释字段编码；不读取参考答案，不用模糊匹配修正语义。"""
from copy import deepcopy
import math


def normalize_output(task, output):
    contract = task['output_contract']
    types = contract['finding_types']
    if set(types) != set(task['requested_findings']):
        raise ValueError('public encoding contract coverage mismatch')
    value = deepcopy(output)
    changes, errors = [], []
    if not isinstance(value, dict) or not isinstance(value.get('findings'), list):
        return {'status': 'invalid', 'changes': [], 'errors': ['findings'], 'normalized': value}
    for row in value['findings']:
        if not isinstance(row, dict) or row.get('id') not in types:
            errors.append('unknown-field'); continue
        field, item = row['id'], row.get('value')
        kind = types[field]
        if kind == 'edge':
            if isinstance(item, list) and len(item) == 1 and isinstance(item[0], list) and len(item[0]) == 2:
                item = item[0]; changes.append({'field': field, 'operation': 'unwrap-single-edge'})
            if isinstance(item, list) and len(item) == 2 and all(isinstance(v, str) for v in item):
                aliases = contract.get('edge_label_aliases', {}).get(field, {})
                mapped = [aliases.get(v, v) for v in item]
                if mapped != item: changes.append({'field': field, 'operation': 'public-edge-label-alias'})
                item = mapped
        valid = ((kind == 'number' and type(item) in (int, float) and math.isfinite(item))
            or (kind == 'boolean' and type(item) is bool)
            or (kind == 'string' and isinstance(item, str) and bool(item.strip()))
            or (kind in ('set', 'ordered', 'edge') and isinstance(item, list)
                and all(isinstance(v, str) and bool(v.strip()) for v in item)
                and len(set(item)) == len(item) and (kind != 'edge' or len(item) == 2)))
        labels = contract.get('allowed_labels', {}).get(field)
        if valid and labels is not None:
            valid = all(v in labels for v in (item if isinstance(item, list) else [item]))
        if not valid: errors.append(field)
        row['value'] = item
    return {'status': 'invalid' if errors else 'normalized' if changes else 'canonical',
            'changes': changes, 'errors': errors, 'normalized': value}
