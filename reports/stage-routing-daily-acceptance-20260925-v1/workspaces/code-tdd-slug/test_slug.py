"""slugify 的行为测试，只用标准库 unittest，可直接被 pytest 收集。"""

import unittest

from slug import slugify


class TestSlugifyLatin(unittest.TestCase):
    def test_lowercases_latin_letters(self):
        self.assertEqual(slugify("Hello World"), "hello-world")

    def test_mixed_case(self):
        self.assertEqual(slugify("PyThOn ROCKS"), "python-rocks")

    def test_digits_are_preserved(self):
        self.assertEqual(slugify("Python 3.12"), "python-3-12")


class TestSlugifySeparators(unittest.TestCase):
    def test_collapses_consecutive_whitespace(self):
        self.assertEqual(slugify("hello    world"), "hello-world")

    def test_collapses_consecutive_punctuation(self):
        self.assertEqual(slugify("Hello, World!!!"), "hello-world")

    def test_collapses_mixed_whitespace_and_punctuation(self):
        self.assertEqual(slugify("a -_- b"), "a-b")

    def test_strips_leading_and_trailing_hyphens(self):
        self.assertEqual(slugify("--hello--"), "hello")

    def test_strips_surrounding_whitespace(self):
        self.assertEqual(slugify("  hello world  "), "hello-world")

    def test_underscore_and_slash_act_as_separators(self):
        self.assertEqual(slugify("a/b_c"), "a-b-c")

    def test_single_word_unchanged(self):
        self.assertEqual(slugify("hello"), "hello")


class TestSlugifyChinese(unittest.TestCase):
    def test_keeps_chinese_characters(self):
        self.assertEqual(slugify("你好世界"), "你好世界")

    def test_mixes_chinese_and_latin(self):
        self.assertEqual(slugify("Hello 世界"), "hello-世界")

    def test_chinese_punctuation_becomes_separator(self):
        self.assertEqual(slugify("你好，世界"), "你好-世界")

    def test_chinese_and_ascii_punctuation(self):
        self.assertEqual(slugify("你好, World!"), "你好-world")


class TestSlugifyUnicodeNormalization(unittest.TestCase):
    def test_fullwidth_latin_is_normalized(self):
        self.assertEqual(slugify("Ｈｅｌｌｏ　Ｗｏｒｌｄ"), "hello-world")

    def test_fullwidth_digits_are_normalized(self):
        self.assertEqual(slugify("ＡＢＣ１２３"), "abc123")

    def test_combining_marks_are_composed(self):
        self.assertEqual(slugify("Cafe\u0301"), "café")

    def test_precomposed_accent_is_kept(self):
        self.assertEqual(slugify("Café"), "café")


class TestSlugifyEmptyResults(unittest.TestCase):
    def test_empty_string(self):
        self.assertEqual(slugify(""), "")

    def test_only_whitespace(self):
        self.assertEqual(slugify("   \t\n"), "")

    def test_only_punctuation(self):
        self.assertEqual(slugify("!!!---___"), "")

    def test_fullwidth_space_only(self):
        self.assertEqual(slugify("　　"), "")


class TestSlugifyContract(unittest.TestCase):
    def test_idempotent_on_valid_slug(self):
        for text in ["Hello, World!", "你好，世界", "Python 3.12"]:
            with self.subTest(text=text):
                self.assertEqual(slugify(slugify(text)), slugify(text))

    def test_result_has_no_leading_or_trailing_hyphen(self):
        for text in ["--a--", "!!!", "  ", "你好！", "-a-b-"]:
            with self.subTest(text=text):
                result = slugify(text)
                self.assertFalse(result.startswith("-"))
                self.assertFalse(result.endswith("-"))

    def test_rejects_non_string(self):
        with self.assertRaises(TypeError):
            slugify(None)
        with self.assertRaises(TypeError):
            slugify(123)


if __name__ == "__main__":
    unittest.main()
