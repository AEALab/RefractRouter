import unittest

from slug import slugify


class SlugifyTest(unittest.TestCase):
    def test_lowercases_latin(self):
        self.assertEqual(slugify("Hello World"), "hello-world")

    def test_consecutive_whitespace_and_punct_to_one_hyphen(self):
        self.assertEqual(slugify("Hello  ,  World!"), "hello-world")

    def test_preserves_chinese(self):
        self.assertEqual(slugify("你好，世界！"), "你好-世界")

    def test_strips_leading_and_trailing_hyphens(self):
        self.assertEqual(slugify("--Hello World--"), "hello-world")
        self.assertEqual(slugify("  Hello  "), "hello")

    def test_empty_result_returns_empty_string(self):
        self.assertEqual(slugify(""), "")
        self.assertEqual(slugify("!!!  ???"), "")
        self.assertEqual(slugify("---"), "")

    def test_unicode_normalization(self):
        # 全角字符经 NFKC 规范化后转半角
        self.assertEqual(slugify("ＡＢＣ"), "abc")

    def test_mixed(self):
        self.assertEqual(slugify("Hello，你好 World"), "hello-你好-world")


if __name__ == "__main__":
    unittest.main()
