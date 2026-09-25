"""slugify 单元测试。使用标准库 unittest，无外部依赖。"""

import sys
import unittest
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from slug import slugify  # noqa: E402


class SlugifyTest(unittest.TestCase):
    def test_empty_string(self):
        self.assertEqual(slugify(""), "")

    def test_only_separators(self):
        self.assertEqual(slugify("   "), "")
        self.assertEqual(slugify("!!!"), "")
        self.assertEqual(slugify("- - -"), "")

    def test_latin_lowercase(self):
        self.assertEqual(slugify("Hello World"), "hello-world")

    def test_consecutive_whitespace_collapsed(self):
        self.assertEqual(slugify("hello    world"), "hello-world")

    def test_punctuation_becomes_hyphen(self):
        self.assertEqual(slugify("hello, world!"), "hello-world")
        self.assertEqual(slugify("a/b\\c"), "a-b-c")

    def test_leading_trailing_hyphens_stripped(self):
        self.assertEqual(slugify("--hello--"), "hello")
        self.assertEqual(slugify("!!hello!!"), "hello")

    def test_mixed_separators_collapsed(self):
        self.assertEqual(slugify("a  ,  b"), "a-b")
        self.assertEqual(slugify("a.,.,b"), "a-b")

    def test_chinese_preserved(self):
        self.assertEqual(slugify("你好世界"), "你好世界")

    def test_chinese_with_latin_and_separators(self):
        self.assertEqual(slugify("你好，World"), "你好-world")

    def test_accents_normalized(self):
        self.assertEqual(slugify("café"), "cafe")
        self.assertEqual(slugify("naïve"), "naive")

    def test_unicode_normalization(self):
        # 全角字符经 NFKD 规范化后转为半角
        self.assertEqual(slugify("ＡＢＣ"), "abc")

    def test_none_returns_empty(self):
        self.assertEqual(slugify(None), "")

    def test_digits_kept(self):
        self.assertEqual(slugify("v2 release"), "v2-release")

    def test_non_latin_letters_as_separator(self):
        # 西里尔字母等非拉丁字母不保留，作为分隔符
        self.assertEqual(slugify("привет world"), "world")
        # 首尾分隔符被去除
        self.assertEqual(slugify("привет"), "")

    def test_fullwidth_punctuation(self):
        # 中文标点经 NFKD 规范化后转为半角并成为分隔符
        self.assertEqual(slugify("你好，世界！"), "你好-世界")


if __name__ == "__main__":
    unittest.main()
