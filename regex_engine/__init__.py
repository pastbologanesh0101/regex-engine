"""regex_engine: a small regular expression engine built from scratch.

Public API (mirrors the shape of Python's ``re`` module, but every bit of
matching logic here is our own -- no use of the ``re`` module):

    import regex_engine

    rx = regex_engine.compile(r"(ab|cd)+")
    rx.match("abcdab")     -> MatchObject or None, anchored at position 0
    rx.search("xxabcdxx")  -> MatchObject or None, anywhere in the string
    rx.findall("ababcdcd") -> list[str] of all non-overlapping matches

See README.md for the supported syntax, how the parser/compiler/matcher
pipeline works, and worked examples.
"""

from .parser import Parser, RegexSyntaxError
from .nfa import compile_to_nfa
from .matcher import CompiledRegex, MatchObject


def compile(pattern):
    """Parse and compile ``pattern`` into a CompiledRegex."""
    ast = Parser(pattern).parse()
    start_state, match_state = compile_to_nfa(ast)
    return CompiledRegex(pattern, ast, start_state, match_state)


__all__ = ["compile", "CompiledRegex", "MatchObject", "RegexSyntaxError"]
