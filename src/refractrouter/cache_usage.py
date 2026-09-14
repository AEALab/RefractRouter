"""缓存计数的可观测性；缺字段不等于供应商报告零命中。"""


def cache_usage(usage, input_tokens, *, detail_keys=('prompt_tokens_details', 'input_tokens_details')):
    if not isinstance(usage, dict):
        return 0, None, True
    found = []
    for key in detail_keys:
        details = usage.get(key)
        if key in usage and not isinstance(details, dict):
            return 0, None, False
        if isinstance(details, dict) and 'cached_tokens' in details:
            found.append((details['cached_tokens'], key + '.cached_tokens'))
    if 'prompt_cache_hit_tokens' in usage:
        found.append((usage['prompt_cache_hit_tokens'], 'prompt_cache_hit_tokens'))
    if not found:
        return 0, None, True
    valid = (type(input_tokens) is int and input_tokens >= 0
             and all(type(value) is int and 0 <= value <= input_tokens for value, _ in found)
             and len({value for value, _ in found if type(value) is int}) == 1)
    return (found[0][0] if valid else 0), (found[0][1] if valid else None), valid
