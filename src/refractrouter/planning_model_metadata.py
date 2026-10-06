"""为规划路由查询可核对的模型容量与实际计价，不以参考价冒充账单价格。"""
from .ark_plan import catalog as ark_plan_catalog
from .dsh_model_pool import frozen_usd_cny_rate, load_frozen_profiles
from .deepseek_official_pricing import pricing as deepseek_cny_pricing


def lookup(request):
    if request.get('billingUnit') == 'REFERENCE':
        from .subscription_reference import ARK_ENDPOINT, reference_for
        endpoint = request.get('providerBaseURL') or ''
        if endpoint.rstrip('/') == ARK_ENDPOINT:
            result = _subscription_lookup({**request, 'billingMode': 'subscription',
                'referencePricing': reference_for(request['model']), 'billingUnit': 'AUTO'})
            if result['billingUnit'] == 'USD':
                rate, fx = frozen_usd_cny_rate()
                result.update(billingUnit='CNY', sourceBillingUnit='USD', exchangeRate=fx,
                    pricing={key: value * rate for key, value in result['pricing'].items()})
            return result
        return lookup({**request, 'billingUnit': 'AUTO'})
    if request.get('billingMode') == 'subscription':
        return _subscription_lookup(request)
    provider, model, unit = (request.get(key) for key in ("provider", "model", "billingUnit"))
    if not all(isinstance(value, str) and value for value in (provider, model, unit)):
        raise ValueError("模型资料查询需要 provider、model 和计费单位")
    if unit not in ("USD", "AFP", "CNY", "AUTO"):
        raise ValueError("不支持的计费单位")
    host = request.get("host") or {}
    if not isinstance(host, dict):
        raise ValueError("宿主模型资料无效")
    result = {"provider": provider, "model": model, "billingUnit": unit,
              "capacity": None, "pricing": None, "capabilities": None, "sources": {}, "issues": []}
    context, output = host.get("contextWindow"), host.get("maxOutputTokens")
    if type(context) is int and context >= 512 and type(output) is int and 0 < output < context:
        result["capacity"] = {"contextWindow": context, "maxOutputTokens": output}
        result["sources"]["capacity"] = "DSH 模型适配器"
    modalities = host.get("inputModalities")
    modalities = modalities if isinstance(modalities, list) and all(isinstance(item, str) for item in modalities) else []
    result["capabilities"] = {"mainExecutor": True, "toolCalling": "connected",
        "modalities": {"imageInput": "connected" if "image" in modalities else "unknown",
                       "videoInput": "unknown", "imageOutput": "unknown", "videoOutput": "unknown"},
        "formats": {}, "limits": {}, "source": "DSH 模型适配器",
        "checkedAt": request.get("checkedAt") or "2026-09-26"}
    ark_plan_route = provider == "ark-plan" or request.get("providerBaseURL") == \
        "https://ark.cn-beijing.volces.com/api/plan/v3"
    if unit == "AUTO":
        unit = "AFP" if ark_plan_route else "CNY"
        result["billingUnit"] = unit
    if ark_plan_route:
        ark = ark_plan_catalog()
        row = next((entry for entry in ark["models"] if entry["model_id"] == model
                    and entry["capability"] == "text-generation"), None)
        if row and result["capacity"] is None:
            result["capacity"] = {"contextWindow": row["context_window_tokens"],
                                  "maxOutputTokens": row["max_output_tokens"]}
            result["sources"]["capacity"] = ark["source_url"]
        if row and unit == "AFP":
            prices = row["pricing"]
            result["pricing"] = {"inputPer1k": prices["input_coefficient"] / 10,
                                 "outputPer1k": prices["output_coefficient"] / 10,
                                 "cachedInputPer1k": prices["input_coefficient"] / 10}
            result["sources"]["pricing"] = row.get("pricing_source_url", ark["pricing_url"])
            result["sources"]["pricingCheckedAt"] = row.get("pricing_checked_at", "2026-09-12")
    else:
        if (provider == "moonshot" and model == "kimi-k3" and unit == "CNY"
                and request.get("providerBaseURL") == "https://api.moonshot.cn/v1"):
            # 官方缓存合同：读、写、未缓存输入互斥；默认 5m 写入与普通输入同价。
            result["pricing"] = {"inputPer1k": .02, "cachedInputPer1k": .002, "outputPer1k": .1}
            result["sources"].update(pricing="https://platform.moonshot.cn/docs/pricing/chat",
                pricingCheckedAt="2026-10-04",
                pricingNote="Kimi 官方 CNY；默认 5m 缓存写入与未缓存输入同价，互斥计量，不重复加收。"
                "当前适配未开启 1h TTL；费用按返回用量估算，以官方账单为准。",
                cacheAccounting="https://platform.moonshot.cn/docs/guide/context-caching")
        official_cny = deepseek_cny_pricing(model) if provider == "deepseek-official" and unit == "CNY" else None
        if official_cny:
            result["pricing"] = {key: official_cny[key] for key in
                                 ("inputPer1k", "outputPer1k", "cachedInputPer1k")}
            result["sources"]["pricing"] = official_cny["source"]
            result["sources"]["pricingCheckedAt"] = official_cny["checkedAt"]
            result["sources"]["pricingNote"] = (
                "DeepSeek 官方人民币价，按北京时间周一至周五及已核对节假日峰谷时段估算；"
                "预算预留采用高峰上界，实际扣费以 DeepSeek 账单为准")
        frozen = load_frozen_profiles()
        row = next((entry for entry in frozen["profiles"]
                    if entry["provider"] == provider and entry["model"] == model), None)
        if result["pricing"] is None and row and row.get("pricing_basis", {}).get("actualProviderBilling") is True \
                and row.get("pricing", {}).get("unit") == "USD" and unit in ("USD", "CNY"):
            prices = row["pricing"]
            multiplier = 1
            if unit == "CNY":
                multiplier, exchange = frozen_usd_cny_rate()
                result["sources"]["conversion"] = exchange["source"]
                result["sources"]["conversionAsOf"] = exchange["as_of"]
            result["pricing"] = {key: prices[key] * multiplier for key in
                                 ("inputPer1k", "outputPer1k", "cachedInputPer1k")}
            source = next((item for item in row.get("sources", []) if item.get("kind") == "official-pricing"), None)
            result["sources"]["pricing"] = source["url"] if source else "冻结官方价格档案"
            result["sources"]["pricingCheckedAt"] = source["retrieved_at"] if source else frozen["frozen_at"]
            if unit == "CNY":
                result["sources"]["pricingNote"] = "按冻结汇率折算的预算价，不代表提供方实际人民币结算价"
    if result["capacity"] is None:
        result["issues"].append("上下文与输出容量待核对")
    if result["pricing"] is None:
        if ark_plan_route and unit != "AFP":
            result["issues"].append(
                f"Ark Agent Plan 按 AFP 计量；当前预算单位 {unit}，不能把订阅点数当作现金价格")
        else:
            result["issues"].append(f"没有 {unit} 单位下可核对的实际路线价格")
    profiles = load_frozen_profiles()
    profile = next((row for row in profiles["profiles"]
        if row["provider"] == provider and row["model"] == model), {})
    result["automaticRouting"] = {"qualityProfile": profile.get("quality_profile"),
        "issues": [*result["issues"], *([] if profile.get("quality_profile") else ["缺少自动路由所需的独立质量资料；不影响规划路由指定使用"]) ]}
    return result


def _subscription_lookup(request):
    """容量仍由实际宿主提供；参考价来源不改变执行渠道及能力。"""
    from .currency_pricing import PriceSnapshot, subscription_valuation, reference_price
    reference = request.get('referencePricing')
    if not isinstance(reference, dict):
        raise ValueError('订阅模型缺少参考价格映射')
    actual = request.get('providerBaseURL')
    endpoint = reference.get('executionEndpoint')
    if not isinstance(actual, str) or not isinstance(endpoint, str) or actual.rstrip('/') != endpoint.rstrip('/'):
        raise ValueError('订阅参考价格绑定的执行端点与宿主实际端点不一致')
    snapshot = reference_price(reference)
    if reference.get('schedule') and snapshot.currency != 'CNY':
        raise ValueError('参考阶梯目前需要 CNY 价格')
    rate, fx = frozen_usd_cny_rate()
    subscription_valuation({'provider': request.get('provider'), 'model': request.get('model'),
        'endpoint': endpoint, 'billingMode': 'subscription'}, snapshot, {},
        mapping=reference.get('mapping'), usd_cny={'base': 'USD', 'quote': 'CNY',
        'rate': rate, 'source': fx['source'], 'asOf': fx['as_of']})
    rates = dict(snapshot.rates)
    if set(rates) - {'input', 'cachedInput', 'cacheWrite', 'output', 'request'} or rates.get('request', 0):
        raise ValueError('文本订阅估值尚不支持附加请求或媒体价格')
    # 先从原执行目录取容量，不能把参考提供方的较大容量复制给实际路线。
    original = lookup({**request, 'billingMode': 'metered', 'billingUnit': 'AUTO'})
    original.update(billingUnit=snapshot.currency, billingMode='subscription',
        pricingBasis='reference-price', referencePricing=reference,
        pricing={'inputPer1k': float(rates['input'] * 1000),
                 'outputPer1k': float(rates['output'] * 1000),
                 'cachedInputPer1k': float(rates.get('cachedInput', rates['input']) * 1000),
                 'cacheWritePer1k': float(rates.get('cacheWrite', rates['input']) * 1000)})
    original['sources'].update(pricing=snapshot.source, pricingCheckedAt=snapshot.checked_at,
        pricingNote='订阅调用的公开价格参考估值，不代表现金扣款；容量来自实际执行路线。')
    # AUTO 的计价缺项已由本次校验过的参考价格替代；其他能力缺项保留。
    original['issues'] = [issue for issue in original['issues']
                          if '价格' not in issue and 'AFP 计量' not in issue]
    return original
