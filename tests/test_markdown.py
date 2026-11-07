import unittest

from wikitools import markdown


class MarkdownTest(unittest.TestCase):
    def test_split_code_keeps_shape(self):
        text = 'a [[x]]\n```bash\nif [[ -n "$v" ]]; then\n```\nb `[[y]]` c\n'
        prose, code = markdown.split_code(text)
        self.assertEqual(len(prose), len(text))
        self.assertEqual(len(code), len(text))
        self.assertEqual(prose.count("\n"), text.count("\n"))
        self.assertIn("[[x]]", prose)
        self.assertNotIn("[[ -n", prose)
        self.assertNotIn("[[y]]", prose)
        self.assertIn("[[ -n", code)
        self.assertIn("[[y]]", code)
        self.assertNotIn("[[x]]", code)

    def test_wikilinks_with_alias_and_heading(self):
        text = "see [[entities/a|A]] and [[concepts/b#Case]]\n\n[[sources/c]]\n"
        self.assertEqual(markdown.wikilinks(text),
                         [(1, "entities/a"), (1, "concepts/b"), (3, "sources/c")])

    def test_tilde_fence_and_longer_closing_fence(self):
        self.assertEqual(markdown.wikilinks("~~~\n[[a]]\n~~~~\n[[b]]\n"), [(4, "b")])

    def test_fence_needs_matching_character(self):
        self.assertEqual(markdown.wikilinks("```\n~~~\n[[a]]\n```\n[[b]]\n"), [(5, "b")])

    def test_bash_double_brackets_are_not_links(self):
        text = "Run:\n\n```bash\n[[ -f x ]] && echo ok\n```\n\nand `[[ -z $y ]]` inline.\n"
        self.assertEqual(markdown.wikilinks(text), [])

    def test_prose_paragraphs(self):
        text = ("# Title\n\nFirst paragraph line one\ncontinues here.\n\n- list item\n\n"
                "| a | b |\n\n```\ncode\n```\n\nLast one.\n")
        self.assertEqual(markdown.prose_paragraphs(text),
                         [(3, "First paragraph line one continues here."), (14, "Last one.")])

    def test_prose_paragraphs_offset(self):
        self.assertEqual(markdown.prose_paragraphs("\nHello there.\n", first_line=6),
                         [(7, "Hello there.")])


    def test_fences_indented_under_list_items(self):
        text = ("- step one\n\n     ```bash\n     [[ -d /etc/pve ]] && echo ok\n     ```\n\n"
                "2. step two\n    ~~~\n    [[x]]\n    ~~~\n\n[[a]]\n")
        self.assertEqual(markdown.wikilinks(text), [(12, "a")])

    def test_shell_tests_outside_fences_are_not_links(self):
        text = "    if [[ -d /etc/pve ]]; then\n\n    [[-d /x]] || exit 1\n\nSee [[b]].\n"
        self.assertEqual(markdown.wikilinks(text), [(5, "b")])


if __name__ == "__main__":
    unittest.main()
