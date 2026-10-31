"""规划调用的原生输出合同与统一费用上界；不选择模型，也不缩减输出。"""
from copy import deepcopy
from dataclasses import replace
import math
import re

VERSION = 'planning-native-output-budget-v1'
SCOPES = ('answer-only', 'answer-and-reasoning-total', 'unknown')
PARAMETERS = ('max_tokens', 'max_completion_tokens', 'max_output_tokens', 'host-maxTokens')


def output_contract(raw, context_window):
    """缺少旧配置声明时只采用全上下文保护，不伪造参数已验证。"""
    if raw is None:
        return {'scope':'unknown','parameter':'host-maxTokens','contextTokens':context_window,
                'sourceSha256':None}
    if (type(raw) is not dict or set(raw)-{'scope','parameter','contextTokens','sourceSha256'}
            or not {'scope','parameter','sourceSha256'}<=set(raw)):
        raise ValueError('outputBudget 字段不完整或存在未知字段')
    scope,parameter=raw['scope'],raw['parameter']
    context=raw.get('contextTokens',context_window)
    source=raw['sourceSha256']
    if scope not in SCOPES or parameter not in PARAMETERS:
        raise ValueError('outputBudget 输出语义或参数无效')
    if type(context) is not int or not context_window<=context<=10_000_000:
        raise ValueError('outputBudget 总上下文包络无效')
    if source is not None and (type(source) is not str or re.fullmatch('[0-9a-f]{64}',source) is None):
        raise ValueError('outputBudget 需要有效来源摘要')
    if scope!='unknown' and source is None:
        raise ValueError('已声明输出语义必须绑定审核来源摘要')
    return {'scope':scope,'parameter':parameter,'contextTokens':context,'sourceSha256':source}


def conservative_model(model):
    """预检与预留共用相同最高价；结算仍使用派发时价格或实际输入阶梯。"""
    if model.provider=='deepseek-official' and model.billing_unit=='CNY':
        from .deepseek_official_pricing import pricing
        rates=pricing(model.api_model,conservative=True)
        if rates:
            model=replace(model,input_cost_per_1k=max(model.input_cost_per_1k,rates['inputPer1k']),
                cached_input_cost_per_1k=max(model.cached_input_cost_per_1k or 0,rates['cachedInputPer1k']),
                output_cost_per_1k=max(model.output_cost_per_1k,rates['outputPer1k']))
    reference=getattr(model,'reference_pricing',None)
    if reference:
        from .currency_pricing import reference_price
        rates=dict(reference_price(reference).rates)
        factor=getattr(model,'conversion_rate',None) or 1
        model=replace(model,input_cost_per_1k=max(model.input_cost_per_1k,float(rates['input'])*1000*factor),
            cached_input_cost_per_1k=max(model.cached_input_cost_per_1k or 0,float(rates.get('cachedInput',rates['input']))*1000*factor),
            cache_write_cost_per_1k=max(getattr(model,'cache_write_cost_per_1k',None) or 0,float(rates.get('cacheWrite',rates['input']))*1000*factor),
            output_cost_per_1k=max(model.output_cost_per_1k,float(rates['output'])*1000*factor))
    return model


def reservation_bound(model, input_bound, output_cap=None, *, check_context=True):
    """总输出合同保护输入＋全部输出；回答或未知合同保护完整共享上下文。"""
    if type(input_bound) is not int or input_bound<0:
        raise ValueError('原生预留输入包络无效')
    native=model.max_output_tokens
    if type(native) is not int or native<=0 or type(model.context_window) is not int:
        raise ValueError('规划模型缺少原生容量')
    if output_cap is not None and (type(output_cap) is not int or output_cap<=0):
        raise ValueError('无效输出容量')
    wire=min(native,output_cap) if output_cap is not None else native
    if check_context and input_bound+wire>model.context_window:
        raise ValueError('request exceeds conservative context bound；上下文容量不足')
    contract=output_contract(getattr(model,'output_budget',None),model.context_window)
    priced=conservative_model(model)
    prices=[priced.input_cost_per_1k,priced.cached_input_cost_per_1k,
        getattr(priced,'cache_write_cost_per_1k',None),priced.output_cost_per_1k]
    if any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in prices if v is not None):
        raise ValueError('原生预留价格无效')
    input_price=max(v for v in prices[:3] if v is not None)
    output_price=prices[3]
    shared=contract['scope']!='answer-and-reasoning-total'
    total=contract['contextTokens']
    if shared:
        cost=total/1000*max(input_price,output_price)
    elif check_context:
        cost=input_bound/1000*input_price+wire/1000*output_price
    else:
        # 尚未生成的输入与全部输出共享上下文，在两个各自上界内先分配较贵的一侧。
        if input_price>=output_price:
            inputs=min(input_bound,total);outputs=min(wire,total-inputs)
        else:
            outputs=min(wire,total);inputs=min(input_bound,total-outputs)
        cost=inputs/1000*input_price+outputs/1000*output_price
    return {'schemaVersion':VERSION,'contract':deepcopy(contract),'wireOutputTokens':wire,
        'inputBound':input_bound,'reservedTotalOutputTokens':total if shared else wire,
        'protectedTotalTokens':total,'scopeVerified':contract['scope']!='unknown',
        'reservationBasis':'native-shared-context' if shared else 'native-total-output',
        'pricesPer1k':{'input':input_price,'output':output_price},'amount':cost}
