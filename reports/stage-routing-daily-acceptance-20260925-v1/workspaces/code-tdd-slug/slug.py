"""把任意文本转换为 URL 友好的 slug。

行为规范见 SPEC.md：

- 先做 Unicode 规范化（NFKC）；
- 拉丁字母转小写；
- 连续空白或标点折叠成一个连字符；
- 保留中文字符；
- 去掉首尾连字符；
- 空结果返回空字符串。

只依赖 Python 标准库。
"""

from __future__ import annotations

import unicodedata

SEPARATOR = "-"


def slugify(text):
    """按 SPEC.md 规则把 ``text`` 转成 slug，无法得到有效字符时返回 ""。"""
    if not isinstance(text, str):
        raise TypeError(f"slugify() 需要 str，收到 {type(text).__name__}")

    # 规范化：NFKC 展开全角字母、兼容字符，并合并组合字符（如 e + ́ → é）。
    normalized = unicodedata.normalize("NFKC", text)

    parts = []
    pending_separator = False
    for char in normalized:
        if char.isalnum():
            # 只有前面已经产出内容时才补连字符，天然去掉首部连字符。
            if pending_separator and parts:
                parts.append(SEPARATOR)
            pending_separator = False
            # 只对拉丁字母生效；中文等无大小写字符不受影响。
            parts.append(char.lower())
        else:
            # 空白或标点：先记为待插入连字符，连续多个只保留一个。
            pending_separator = True

    # 尾部待插入的连字符被直接丢弃。
    return "".join(parts)
