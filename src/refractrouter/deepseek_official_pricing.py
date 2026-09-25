"""DeepSeek 官方中文价格快照；人民币与 Ark AFP 分账。"""
from datetime import datetime, time
from zoneinfo import ZoneInfo

SOURCE = "https://api-docs.deepseek.com/zh-cn/quick_start/pricing"
CHECKED_AT = "2026-09-24"
_PER_MILLION = {
    "deepseek-flash": {"offpeak": (1, 4, .02), "peak": (2, 8, .04)},
    "deepseek-v4-pro": {"offpeak": (4.5, 13.5, .15), "peak": (9, 27, .30)},
}
_ALIASES = {"deepseek-v4-flash": "deepseek-flash",
            "deepseek-v4-flash-vision-exp": "deepseek-flash"}


def pricing(model, *, at=None, conservative=False):
    """返回每千 token 人民币价；保守预留始终采用高峰价。"""
    name = _ALIASES.get(model, model)
    if name not in _PER_MILLION:
        return None
    now = at or datetime.now(ZoneInfo("Asia/Shanghai"))
    if now.tzinfo is None:
        raise ValueError("DeepSeek 价格时段需要带时区的时间")
    local = now.astimezone(ZoneInfo("Asia/Shanghai"))
    hour = local.time()
    peak_window = local.weekday() < 5 and (time(9) <= hour < time(12)
        or time(14) <= hour < time(18))
    tier = "peak-upper-bound" if conservative else "peak" if peak_window else "offpeak"
    missing, output, hit = _PER_MILLION[name]["peak" if tier != "offpeak" else "offpeak"]
    return {"inputPer1k": missing / 1000, "outputPer1k": output / 1000,
            "cachedInputPer1k": hit / 1000, "tier": tier, "source": SOURCE,
            "checkedAt": CHECKED_AT}
