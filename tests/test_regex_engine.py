"""Unit tests for regex_engine.

Notably:
  * `re` (Python's real regex module) is imported ONLY in
    TestCrossCheckAgainstRe, and only ever used to compute a reference
    answer to compare our engine's output against -- never anywhere in the
    engine implementation itself.
  * TestPathologicalBacktracking asserts that a classically catastrophic
    pattern completes in a short, bounded time, proving the engine does
    not do naive exponential backtracking.
"""

import re
import time
import unittest

import regex_engine


def m(pattern, text):
    return regex_engine.compile(pattern).match(text)


def s(pattern, text):
    return regex_engine.compile(pattern).search(text)


def fa(pattern, text):
    return regex_engine.compile(pattern).findall(text)


class TestLiteralMatching(unittest.TestCase):
    def test_exact_literal_match(self):
        r = m("hello", "hello")
        self.assertIsNotNone(r)
        self.assertEqual(r.span(), (0, 5))
        self.assertEqual(r.group(), "hello")

    def test_literal_mismatch(self):
        self.assertIsNone(m("hello", "world"))

    def test_literal_prefix_match_only(self):
        # match() anchors at start but does not require consuming the
        # whole string, mirroring re.match.
        r = m("he", "hello")
        self.assertIsNotNone(r)
        self.assertEqual(r.group(), "he")

    def test_escaped_metacharacter_literal(self):
        r = m(r"a\.b", "a.b")
        self.assertIsNotNone(r)
        self.assertEqual(r.group(), "a.b")
        self.assertIsNone(m(r"a\.b", "axb"))


class TestConcatenation(unittest.TestCase):
    def test_simple_concat(self):
        self.assertIsNotNone(m("abc", "abc"))

    def test_concat_with_groups(self):
        r = m("(ab)(cd)", "abcd")
        self.assertIsNotNone(r)
        self.assertEqual(r.group(), "abcd")


class TestAlternation(unittest.TestCase):
    def test_alternation_matches_either_branch(self):
        rx = regex_engine.compile("cat|dog")
        self.assertIsNotNone(rx.match("cat"))
        self.assertIsNotNone(rx.match("dog"))
        self.assertIsNone(rx.match("cow"))

    def test_alternation_prefers_leftmost_branch(self):
        # Perl/re-style leftmost-first: 'a' is tried before 'ab', and
        # since 'a' alone already succeeds, match() stops there.
        r = m("a|ab", "ab")
        self.assertEqual(r.group(), "a")

    def test_alternation_of_more_than_two_branches(self):
        rx = regex_engine.compile("red|green|blue")
        self.assertEqual(rx.match("green").group(), "green")
        self.assertEqual(rx.match("blue").group(), "blue")
        self.assertIsNone(rx.match("yellow"))


class TestKleeneStar(unittest.TestCase):
    def test_star_matches_zero_occurrences(self):
        r = m("a*", "bbb")
        self.assertIsNotNone(r)
        self.assertEqual(r.group(), "")

    def test_star_matches_many_occurrences_greedily(self):
        r = m("a*", "aaaab")
        self.assertEqual(r.group(), "aaaa")

    def test_star_on_group(self):
        r = m("(ab)*", "ababab")
        self.assertEqual(r.group(), "ababab")


class TestPlus(unittest.TestCase):
    def test_plus_requires_at_least_one(self):
        self.assertIsNone(m("a+", "bbb"))

    def test_plus_matches_greedily(self):
        r = m("a+", "aaaab")
        self.assertEqual(r.group(), "aaaa")

    def test_plus_matches_single_occurrence(self):
        r = m("a+", "abbb")
        self.assertEqual(r.group(), "a")


class TestOptional(unittest.TestCase):
    def test_optional_present(self):
        r = m("colou?r", "colour")
        self.assertEqual(r.group(), "colour")

    def test_optional_absent(self):
        r = m("colou?r", "color")
        self.assertEqual(r.group(), "color")


class TestGroupingWithAlternation(unittest.TestCase):
    def test_group_alternation_plus(self):
        rx = regex_engine.compile("(ab|cd)+")
        r = rx.match("abcdabcd")
        self.assertIsNotNone(r)
        self.assertEqual(r.group(), "abcdabcd")

    def test_group_alternation_plus_mismatch(self):
        rx = regex_engine.compile("(ab|cd)+")
        self.assertIsNone(rx.match("xyz"))

    def test_group_alternation_plus_partial(self):
        rx = regex_engine.compile("(ab|cd)+")
        r = rx.match("abcdxx")
        self.assertEqual(r.group(), "abcd")


class TestCharacterClasses(unittest.TestCase):
    def test_range_class(self):
        rx = regex_engine.compile("[a-z]+")
        self.assertEqual(rx.match("hello").group(), "hello")
        self.assertIsNone(rx.match("HELLO"))

    def test_negated_class(self):
        rx = regex_engine.compile("[^0-9]+")
        self.assertEqual(rx.match("abc123").group(), "abc")

    def test_enumerated_class(self):
        rx = regex_engine.compile("[abc]+")
        self.assertEqual(rx.match("aabbcc").group(), "aabbcc")
        self.assertIsNone(rx.match("d"))

    def test_class_with_range_and_literal_mix(self):
        rx = regex_engine.compile("[a-cX]+")
        self.assertEqual(rx.match("abcX").group(), "abcX")


class TestWildcard(unittest.TestCase):
    def test_dot_matches_any_char(self):
        r = m("a.c", "abc")
        self.assertIsNotNone(r)
        self.assertEqual(r.group(), "abc")

    def test_dot_does_not_match_newline(self):
        self.assertIsNone(m("a.c", "a\nc"))

    def test_dot_star_greedy(self):
        r = m("a.*z", "axxxz")
        self.assertEqual(r.group(), "axxxz")


class TestAnchors(unittest.TestCase):
    def test_start_anchor_restricts_position(self):
        rx = regex_engine.compile("^abc")
        self.assertIsNotNone(rx.match("abcdef"))
        self.assertIsNone(rx.search("xabcdef"))

    def test_end_anchor_restricts_position(self):
        rx = regex_engine.compile("abc$")
        self.assertIsNotNone(rx.search("xxabc"))
        self.assertIsNone(rx.search("abcxx"))

    def test_start_and_end_anchor_full_match(self):
        rx = regex_engine.compile("^abc$")
        self.assertIsNotNone(rx.match("abc"))
        self.assertIsNone(rx.match("abcd"))
        self.assertIsNone(rx.match("xabc"))


class TestFindall(unittest.TestCase):
    def test_findall_returns_all_non_overlapping_matches(self):
        result = fa("ab", "ababxxabxab")
        self.assertEqual(result, ["ab", "ab", "ab", "ab"])

    def test_findall_no_matches(self):
        self.assertEqual(fa("zzz", "abcdef"), [])

    def test_findall_with_quantifiers(self):
        result = fa("a+", "aaa bb a aa")
        self.assertEqual(result, ["aaa", "a", "aa"])

    def test_findall_with_char_class(self):
        result = fa("[0-9]+", "x12y345z6")
        self.assertEqual(result, ["12", "345", "6"])


class TestPathologicalBacktracking(unittest.TestCase):
    def test_nested_star_does_not_blow_up(self):
        """(a*)*b against a long run of 'a's with no trailing 'b' is the
        textbook case that makes a naive recursive-backtracking engine take
        exponential time. Our Thompson-NFA simulation tracks simultaneous
        states instead of backtracking, so this must finish almost
        instantly regardless of input length.
        """
        rx = regex_engine.compile("(a*)*b")
        text = "a" * 5000  # a naive backtracker would never finish this

        start = time.perf_counter()
        result = rx.search(text)
        elapsed = time.perf_counter() - start

        self.assertIsNone(result)
        self.assertLess(
            elapsed, 2.0,
            f"pathological pattern took {elapsed:.3f}s -- looks like "
            "exponential backtracking, not linear NFA simulation",
        )

    def test_nested_plus_does_not_blow_up(self):
        rx = regex_engine.compile("(a+)+c")
        text = "a" * 5000 + "b"

        start = time.perf_counter()
        result = rx.search(text)
        elapsed = time.perf_counter() - start

        self.assertIsNone(result)
        self.assertLess(elapsed, 2.0)


class TestCrossCheckAgainstRe(unittest.TestCase):
    """Compare our engine's match/search/findall output against Python's
    real `re` module across a wide variety of pattern+string pairs drawn
    from our supported syntax subset. This is the strongest evidence of
    correctness: if our from-scratch engine agrees with the battle-tested
    standard library on dozens of cases, it's very unlikely to be wrong.

    `re` is used here ONLY as a reference oracle for comparison -- never
    inside regex_engine itself.
    """

    CASES = [
        # (pattern, text)
        ("abc", "abc"),
        ("abc", "abcdef"),
        ("abc", "xabc"),
        ("abc", "ab"),
        ("a*", ""),
        ("a*", "aaa"),
        ("a*", "baaa"),
        ("a+", "aaa"),
        ("a+", ""),
        ("a+", "b"),
        ("a?", "a"),
        ("a?", ""),
        ("a?b", "b"),
        ("a?b", "ab"),
        ("cat|dog", "cat"),
        ("cat|dog", "dog"),
        ("cat|dog", "cow"),
        ("cat|dog", "the cat sat"),
        ("a|ab", "ab"),
        ("ab|a", "ab"),
        ("(ab|cd)+", "abcdab"),
        ("(ab|cd)+", "abcdxx"),
        ("(ab|cd)*ef", "ababcdef"),
        ("[a-z]+", "hello"),
        ("[a-z]+", "Hello"),
        ("[A-Za-z]+", "Hello"),
        ("[^0-9]+", "abc123"),
        ("[^a-z]+", "ABC123abc"),
        ("[abc]+", "aabbccdd"),
        ("[a-cX-Z]+", "abcXYZ"),
        (".", "a"),
        (".", ""),
        ("a.c", "abc"),
        ("a.*c", "aXXXc"),
        ("a.*c", "abc def c"),
        ("^abc", "abcdef"),
        ("^abc", "xabcdef"),
        ("abc$", "xxabc"),
        ("abc$", "abcxx"),
        ("^abc$", "abc"),
        ("^abc$", "abcd"),
        ("^a.*z$", "aXYZz"),
        ("(a|b)*c", "ababc"),
        ("(a|b)*c", "aaac"),
        ("(a|b)*c", "d"),
        ("x(yz)+w", "xyzyzw"),
        ("x(yz)+w", "xw"),
        ("[0-9]+-[0-9]+", "12-345"),
        ("[0-9]+\\.[0-9]+", "3.14"),
        ("\\(a\\)", "(a)"),
        ("ab?c", "ac"),
        ("colou?r", "color"),
        ("colou?r", "colour"),
        ("colou?r", "colouur"),
        ("(foo)+(bar)?", "foofoobar"),
        ("(foo)+(bar)?", "foofoo"),
        ("[ab]*[cd]*e", "aabbccdde"),
        ("[ab]*[cd]*e", "e"),
        ("[ab]*[cd]*e", "xyz"),
        ("a*a*a*b", "aaaaaaaaab"),
        ("(a*)*b", "aaab"),
        ("(a*)*b", "aaa"),
    ]

    def _re_findall_full_matches(self, pattern, text):
        # Use finditer + group(0) rather than re.findall, so that
        # capturing groups in `pattern` (which our engine treats as plain,
        # non-capturing grouping) don't change what gets returned.
        return [mo.group(0) for mo in re.finditer(pattern, text)]

    def test_cross_check_match_search_findall(self):
        for pattern, text in self.CASES:
            with self.subTest(pattern=pattern, text=text):
                ours = regex_engine.compile(pattern)
                theirs = re.compile(pattern)

                our_match = ours.match(text)
                their_match = theirs.match(text)
                self.assertEqual(
                    our_match.span() if our_match else None,
                    their_match.span() if their_match else None,
                    f"match() mismatch for pattern={pattern!r} text={text!r}",
                )

                our_search = ours.search(text)
                their_search = theirs.search(text)
                self.assertEqual(
                    our_search.span() if our_search else None,
                    their_search.span() if their_search else None,
                    f"search() mismatch for pattern={pattern!r} text={text!r}",
                )

                our_findall = ours.findall(text)
                their_findall = self._re_findall_full_matches(pattern, text)
                self.assertEqual(
                    our_findall,
                    their_findall,
                    f"findall() mismatch for pattern={pattern!r} text={text!r}",
                )

    def test_cross_check_covers_a_wide_variety(self):
        # Sanity check on the test data itself: make sure the cross-check
        # suite above is actually "decent-sized" and not accidentally
        # trivial/empty.
        self.assertGreaterEqual(len(self.CASES), 40)


class TestSyntaxErrors(unittest.TestCase):
    def test_unbalanced_paren_raises(self):
        with self.assertRaises(regex_engine.RegexSyntaxError):
            regex_engine.compile("(abc")

    def test_dangling_quantifier_raises(self):
        with self.assertRaises(regex_engine.RegexSyntaxError):
            regex_engine.compile("*abc")

    def test_unterminated_class_raises(self):
        with self.assertRaises(regex_engine.RegexSyntaxError):
            regex_engine.compile("[abc")


if __name__ == "__main__":
    unittest.main()
