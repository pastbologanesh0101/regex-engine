"""Hand-written recursive-descent parser for the supported regex subset.

Grammar (highest precedence first, mirroring standard regex precedence:
quantifiers bind tightest, then concatenation, then alternation):

    Alt      := Concat ('|' Concat)*
    Concat   := Repeat*
    Repeat   := Atom ('*' | '+' | '?')?
    Atom     := Literal
              | '.'
              | '(' Alt ')'
              | CharClass
              | '^'
              | '$'
              | '\\' Literal   (escaped literal, e.g. \\* \\. \\( )

Supported syntax (documented precisely in README.md):
    literals, concatenation, '|', '*', '+', '?', '(' ')', '[...]' / '[^...]'
    with 'a-z' ranges, '.', '^', '$', and backslash-escaping of any
    character (mainly useful for the metacharacters above).
"""

from .ast_nodes import (
    Lit,
    Dot,
    CharClassNode,
    Empty,
    Concat,
    Alt,
    Star,
    Plus,
    Optional,
    Group,
    StartAnchor,
    EndAnchor,
)

_SPECIAL = set("|*+?()[].^$\\")


class RegexSyntaxError(Exception):
    """Raised when a pattern string cannot be parsed."""


class Parser:
    def __init__(self, pattern):
        self.pattern = pattern
        self.i = 0
        self.n = len(pattern)

    # -- low level helpers -------------------------------------------------

    def _peek(self):
        return self.pattern[self.i] if self.i < self.n else None

    def _peek_at(self, offset):
        j = self.i + offset
        return self.pattern[j] if j < self.n else None

    def _advance(self):
        c = self._peek()
        self.i += 1
        return c

    # -- public entry point -------------------------------------------------

    def parse(self):
        node = self._parse_alt()
        if self.i != self.n:
            raise RegexSyntaxError(
                f"Unexpected character {self._peek()!r} at position {self.i}"
            )
        return node

    # -- grammar rules -------------------------------------------------------

    def _parse_alt(self):
        branches = [self._parse_concat()]
        while self._peek() == "|":
            self._advance()
            branches.append(self._parse_concat())
        if len(branches) == 1:
            return branches[0]
        return Alt(branches)

    def _parse_concat(self):
        parts = []
        while self._peek() is not None and self._peek() not in ("|", ")"):
            parts.append(self._parse_repeat())
        if not parts:
            return Empty()
        if len(parts) == 1:
            return parts[0]
        return Concat(parts)

    def _parse_repeat(self):
        atom = self._parse_atom()
        c = self._peek()
        if c == "*":
            self._advance()
            return Star(atom)
        if c == "+":
            self._advance()
            return Plus(atom)
        if c == "?":
            self._advance()
            return Optional(atom)
        return atom

    def _parse_atom(self):
        c = self._peek()
        if c is None:
            raise RegexSyntaxError("Unexpected end of pattern")

        if c == "(":
            self._advance()
            node = self._parse_alt()
            if self._peek() != ")":
                raise RegexSyntaxError("Expected ')' to close group")
            self._advance()
            return Group(node)

        if c == "[":
            return self._parse_charclass()

        if c == ".":
            self._advance()
            return Dot()

        if c == "^":
            self._advance()
            return StartAnchor()

        if c == "$":
            self._advance()
            return EndAnchor()

        if c in ("*", "+", "?"):
            raise RegexSyntaxError(
                f"Quantifier {c!r} at position {self.i} has nothing to repeat"
            )

        if c == ")":
            raise RegexSyntaxError(f"Unbalanced ')' at position {self.i}")

        if c == "|":  # pragma: no cover - _parse_concat stops before '|'
            raise RegexSyntaxError(f"Unexpected '|' at position {self.i}")

        if c == "\\":
            self._advance()
            nc = self._peek()
            if nc is None:
                raise RegexSyntaxError("Dangling '\\' at end of pattern")
            self._advance()
            return Lit(nc)

        self._advance()
        return Lit(c)

    # -- character classes ----------------------------------------------------

    def _read_class_char(self):
        c = self._peek()
        if c is None:
            raise RegexSyntaxError("Unterminated character class")
        if c == "\\":
            self._advance()
            nc = self._peek()
            if nc is None:
                raise RegexSyntaxError("Dangling '\\' in character class")
            self._advance()
            return nc
        self._advance()
        return c

    def _parse_charclass(self):
        assert self._peek() == "["
        self._advance()

        negate = False
        if self._peek() == "^":
            negate = True
            self._advance()

        chars = set()
        ranges = []

        if self._peek() is None:
            raise RegexSyntaxError("Unterminated character class")

        while True:
            if self._peek() is None:
                raise RegexSyntaxError("Unterminated character class")
            if self._peek() == "]":
                self._advance()
                break

            lo = self._read_class_char()
            if self._peek() == "-" and self._peek_at(1) not in (None, "]"):
                self._advance()  # consume '-'
                hi = self._read_class_char()
                if ord(hi) < ord(lo):
                    raise RegexSyntaxError(
                        f"Bad character range '{lo}-{hi}' in class"
                    )
                ranges.append((lo, hi))
            else:
                chars.add(lo)

        return CharClassNode(negate, chars, ranges)
