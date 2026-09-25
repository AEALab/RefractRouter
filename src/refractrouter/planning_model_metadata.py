"""为规划路由查询可核对的模型容量与实际计价，不以参考价冒充账单价格。"""
from .ark_plan import catalog as ark_plan_catalog
from .dsh_model_pool import frozen_usd_cny_rate, load_frozen_profiles
from .deepseek_official_pricing import pricing as deepseek_cny_pricing


def lookup(request):
    provider, model, unit = (request.get(key) for key in ("provider", "model", "billingUnit"))
    if not all(isinstance(value, str) and value for value in (provider, model, unit)):
        raise ValueError("模型资料查询需要 provider、model 和计费单位")
    if unit not in ("USD", "AFP", "CNY", "AUTO"):
        raise ValueError("不支持的计费单位")
    host = request.get("host") or {}
    if not isinstance(host, dict):
        raise ValueError("宿主模型资料无效")
    result = {"provider": provider, "model": model, "billingUnit": unit,
              "capacity": None, "pricing": None, "sources": {}, "issues": []}
    context, output = host.get("contextWindow"), host.get("maxOutputTokens")
    if type(context) is int and context >= 512 and type(output) is int and 0 < output < context:
        result["capacity"] = {"contextWindow": context, "maxOutputTokens": output}
        result["sources"]["capacity"] = "DSH 模型适配器"
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
        official_cny = deepseek_cny_pricing(model) if provider == "deepseek-official" and unit == "CNY" else None
        if official_cny:
            result["pricing"] = {key: official_cny[key] for key in
                                 ("inputPer1k", "outputPer1k", "cachedInputPer1k")}
            result["sources"]["pricing"] = official_cny["source"]
            result["sources"]["pricingCheckedAt"] = official_cny["checkedAt"]
            result["sources"]["pricingNote"] = (
                "DeepSeek 官方人民币价，按北京时间工作日峰谷时段估算；"
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
    return result
