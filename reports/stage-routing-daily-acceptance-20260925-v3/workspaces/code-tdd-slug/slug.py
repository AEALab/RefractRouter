import re
import unicodedata


def slugify(text):
    """把文本转换为 URL 友好的 slug 字符串。

    规则（见 SPEC.md）：
    - 进行 Unicode 规范化（NFKC）；
    - 拉丁字母转小写；
    - 连续的空白或标点合并为一个连字符；
    - 保留中文字符；
    - 去掉首尾的连字符；
    - 结果为空时返回空字符串。
    """
    normalized = unicodedata.normalize("NFKC", text).lower()
    parts = []
    for ch in normalized:
        # 保留字母、数字及中文字符，其余（空白、标点等）统一替换为连字符
        if ch.isalnum() or "\u4e00" <= ch <= "\u9fff":
            parts.append(ch)
        else:
            parts.append("-")
    slug = "".join(parts)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")
