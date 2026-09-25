import unittest

from slug import slugify


class SlugifyTest(unittest.TestCase):
    def test_latin_lowercase(self):
        self.assertEqual(slugify("Hello World"), "hello-world")

    def test_consecutive_punctuation_and_whitespace_to_single_hyphen(self):
        self.assertEqual(slugify("Hello,   World!"), "hello-world")

    def test_whitespace_runs_to_single_hyphen(self):
        self.assertEqual(slugify("a   b\t\nc"), "a-b-c")

    def test_accents_preserved_decomposed_form(self):
        # 分解形式 Cafe\u0301 必须输出 café，不能删除组合标记得到 cafe
        self.assertEqual(slugify("Cafe\u0301"), "café")

    def test_accents_preserved_composed_form(self):
        self.assertEqual(slugify("café"), "café")

    def test_chinese_characters_preserved(self):
        self.assertEqual(slugify("你好 世界"), "你好-世界")

    def test_leading_trailing_hyphens_removed(self):
        self.assertEqual(slugify("  Hello  "), "hello")
        self.assertEqual(slugify("--a--"), "a")

    def test_empty_string(self):
        self.assertEqual(slugify(""), "")

    def test_only_punctuation_returns_empty(self):
        self.assertEqual(slugify("!!!..."), "")

    def test_digits_kept(self):
        self.assertEqual(slugify("Version 1.2"), "version-1-2")


if __name__ == "__main__":
    unittest.main()
