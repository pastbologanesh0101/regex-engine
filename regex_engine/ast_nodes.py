"""AST node definitions for the regex parser.

Each node is a small, plain class. Nodes are produced by ``parser.Parser``
and consumed by ``nfa.compile_to_nfa``. None of these classes contain any
matching logic themselves -- they are pure data.
"""


class Node:
    """Base class, only used for isinstance checks / repr conventions."""

    def __repr__(self):  # pragma: no cover - debugging aid only
        fields = ", ".join(f"{k}={v!r}" for k, v in vars(self).items())
        return f"{self.__class__.__name__}({fields})"


class Lit(Node):
    """A single literal character."""

    def __init__(self, c):
        self.c = c


class Dot(Node):
    """The wildcard ``.`` -- matches any character except newline."""


class CharClassNode(Node):
    """A ``[...]`` character class.

    negate: True if the class was written as ``[^...]``
    chars:  a set of individual characters that are members
    ranges: a list of (lo, hi) character tuples, inclusive, e.g. ('a', 'z')
    """

    def __init__(self, negate, chars, ranges):
        self.negate = negate
        self.chars = chars
        self.ranges = ranges


class Empty(Node):
    """Matches the empty string. Used for e.g. an empty group ``()``."""


class Concat(Node):
    """Sequential composition of two or more nodes."""

    def __init__(self, parts):
        self.parts = parts


class Alt(Node):
    """Alternation between two or more branches, e.g. ``cat|dog``."""

    def __init__(self, options):
        self.options = options


class Star(Node):
    """Kleene star: zero or more repetitions, greedy."""

    def __init__(self, node):
        self.node = node


class Plus(Node):
    """One or more repetitions, greedy."""

    def __init__(self, node):
        self.node = node


class Optional(Node):
    """Zero or one repetition, greedy."""

    def __init__(self, node):
        self.node = node


class Group(Node):
    """A parenthesized sub-expression ``(...)``.

    Purely a grouping/precedence marker for the parser; it has no effect on
    the compiled NFA beyond compiling the wrapped node in place.
    """

    def __init__(self, node):
        self.node = node


class StartAnchor(Node):
    """``^`` -- zero-width assertion: only matches at absolute position 0."""


class EndAnchor(Node):
    """``$`` -- zero-width assertion: only matches at the end of the text."""
