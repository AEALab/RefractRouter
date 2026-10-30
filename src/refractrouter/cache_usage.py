"""用量细分的可观测性及别名一致性；缺字段不等于供应商报告零。"""


def total_usage_valid(usage, input_count, output_count):
    for keys, value in ((('prompt_tokens', 'input_tokens'), input_count),
                        (('completion_tokens', 'output_tokens'), output_count)):
        if type(value) is not int or value < 0:
            return False
        for key in keys:
            if key in usage and (type(usage[key]) is not int or usage[key] != value):
                return False
    if 'total_tokens' in usage and (type(usage['total_tokens']) is not int
                                    or usage['total_tokens'] != input_count + output_count):
        return False
    return True


def reasoning_usage(usage, output_count):
    found = []
    for key in ('completion_tokens_details', 'output_tokens_details'):
        detail = usage.get(key)
        if detail is not None and not isinstance(detail, dict):
            return 0, False
        if isinstance(detail, dict) and 'reasoning_tokens' in detail:
            found.append(detail['reasoning_tokens'])
    if not found:
        return 0, True
    valid = (type(output_count) is int and all(type(value) is int and 0 <= value <= output_count for value in found)
             and len({value for value in found if type(value) is int}) == 1)
    return (found[0] if type(found[0]) is int else 0), valid


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


def observed_details(response):
    """只投影有来源的已知细分；缺字段不伪造成零缓存或零思考。"""
    cached = response.cached_input_tokens if response.cache_usage_source is not None else None
    raw = response.raw_usage
    reasoning = None
    if isinstance(raw, dict):
        for key in ("completion_tokens_details", "output_tokens_details"):
            detail = raw.get(key)
            if isinstance(detail, dict) and "reasoning_tokens" in detail:
                value = detail["reasoning_tokens"]
                if type(value) is int and 0 <= value <= response.output_tokens and value == response.reasoning_tokens:
                    reasoning = value
    return cached, reasoning
