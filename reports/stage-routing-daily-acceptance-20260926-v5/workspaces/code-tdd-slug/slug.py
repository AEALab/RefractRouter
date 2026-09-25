import re
import unicodedata


def slugify(text):
    """按 SPEC.md 生成 slug。

    - Unicode 规范化（保留拉丁重音字符，如分解形式 Cafe\\u0301 输出 café）
    - 拉丁字母转小写
    - 连续空白或标点变成一个连字符
    - 保留中文字符
    - 去掉首尾连字符
    - 空结果返回空字符串
    """
    text = unicodedata.normalize("NFKC", text).lower()
    # 字母或数字（含中文）保留，其余（空白、标点、符号）转为连字符
    text = "".join("-" if not ch.isalnum() else ch for ch in text)
    # 合并连续连字符并去掉首尾连字符
    text = re.sub(r"-+", "-", text).strip("-")
    return text
