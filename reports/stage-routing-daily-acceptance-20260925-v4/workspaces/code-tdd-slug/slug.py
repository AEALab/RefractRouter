"""slugify 实现：将文本转换为 URL 友好的短横线 slug。

只依赖 Python 标准库。
"""

import unicodedata


def _is_chinese(char):
    """判断字符是否属于 CJK 统一表意文字区段。"""
    return (
        "\u3400" <= char <= "\u4dbf"  # CJK 扩展 A
        or "\u4e00" <= char <= "\u9fff"  # CJK 统一表意文字
    )


def slugify(text):
    """生成 slug。

    规则：
    - 使用 Unicode 规范化（NFKD）分解组合字符；
    - 丢弃组合标记；
    - 拉丁字母转为小写并保留，保留数字与中文字符；
    - 连续空白或标点等分隔符合并为一个连字符；
    - 去掉首尾连字符；
    - 空结果返回空字符串。
    """
    if text is None:
        return ""

    normalized = unicodedata.normalize("NFKD", str(text))
    pieces = []

    for char in normalized:
        category = unicodedata.category(char)

        # 丢弃组合标记（例如变音符号的分解部分）
        if category.startswith("M"):
            continue

        # 拉丁字母：转为小写并保留
        if "A" <= char <= "Z" or "a" <= char <= "z":
            pieces.append(char.lower())
            continue

        # 数字保留
        if "0" <= char <= "9":
            pieces.append(char)
            continue

        # 中文字符保留
        if _is_chinese(char):
            pieces.append(char)
            continue

        # 其余字符（空白、标点、非拉丁字母等）作为分隔符
        pieces.append("-")

    slug = "".join(pieces)

    # 合并连续连字符，去掉首尾连字符
    slug = _collapse_hyphens(slug)
    return slug.strip("-")


def _collapse_hyphens(slug):
    """将连续连字符合并为单个连字符。"""
    if not slug:
        return slug
    result = []
    prev_dash = False
    for char in slug:
        if char == "-":
            if not prev_dash:
                result.append(char)
            prev_dash = True
        else:
            result.append(char)
            prev_dash = False
    return "".join(result)
