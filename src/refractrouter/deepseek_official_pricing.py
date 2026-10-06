"""DeepSeek 官方人民币价；公开价估算与实际账单保持区分。"""
from datetime import datetime, time
from zoneinfo import ZoneInfo

SOURCE = "https://api-docs.deepseek.com/zh-cn/quick_start/pricing"
CHECKED_AT = "2026-10-06"
CALENDAR_SOURCE = "https://www.beijing.gov.cn/zhengce/zhengcefagui/202511/t20251104_4258873.html"
HOLIDAY_RULE_SOURCE = "https://www.gov.cn/zhengce/content/202411/content_6986380.htm"
# 国办发明电〔2025〕7号；周末调休上班仍是周末，提供方明确按周一至周五计高峰。
BREAK_RANGES = {2026: (("01-01", "01-03"), ("02-15", "02-23"),
                      ("04-04", "04-06"), ("05-01", "05-05"),
                      ("06-19", "06-21"), ("09-25", "09-27"),
                      ("10-01", "10-07"))}
# 调休假期不全是法定节日本日。未经提供方确认，不能把整段调休都套用折扣。
HOLIDAY_RANGES = {2026: (("01-01", "01-01"), ("02-16", "02-19"),
                        ("04-05", "04-05"), ("05-01", "05-02"),
                        ("06-19", "06-19"), ("09-25", "09-25"),
                        ("10-01", "10-03"))}
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
    calendar_verified = local.year in HOLIDAY_RANGES
    month_day = local.strftime("%m-%d")
    holiday = any(start <= month_day <= end
                  for start, end in HOLIDAY_RANGES.get(local.year, ()))
    adjusted_break = not holiday and any(start <= month_day <= end
                        for start, end in BREAK_RANGES.get(local.year, ()))
    peak_window = local.weekday() < 5 and (time(9) <= hour < time(12)
        or time(14) <= hour < time(18)) and not holiday
    tier = "peak-upper-bound" if conservative else "peak" if peak_window else "offpeak"
    if not conservative and peak_window and not calendar_verified:
        tier = "calendar-unverified-upper-bound"
    elif not conservative and peak_window and adjusted_break:
        tier = "holiday-adjustment-unverified-upper-bound"
    missing, output, hit = _PER_MILLION[name]["offpeak" if tier == "offpeak" else "peak"]
    return {"inputPer1k": missing / 1000, "outputPer1k": output / 1000,
            "cachedInputPer1k": hit / 1000, "tier": tier, "source": SOURCE,
            "checkedAt": CHECKED_AT, "calendarVerified": calendar_verified,
            "calendarSource": CALENDAR_SOURCE if calendar_verified else None,
            "holidayRuleSource": HOLIDAY_RULE_SOURCE if calendar_verified else None}
