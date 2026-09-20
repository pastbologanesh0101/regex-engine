"""Thompson's construction: compiles a regex AST into an NFA.

This follows the classic McNaughton-Yamada-Thompson algorithm (see the
"Thompson's construction" section of the README for a full explanation).
Every sub-expression is compiled into a *fragment*: a start state plus a
list of still-unconnected ("dangling") out-pointers. Fragments are wired
together according to the AST shape:

    concatenation   -> patch left fragment's dangling outs to right's start
    alternation     -> a new 'split' state branching into each fragment
    star  (e*)      -> a 'split' that either enters the body or exits,
                       with the body looping back to the split
    plus  (e+)      -> the body runs once, then a 'split' either loops
                       back into the body or exits
    optional (e?)   -> a 'split' that either enters the body or exits
                       directly, both converging afterwards

Each constructed state has O(1) out-edges (at most two, for 'split'), which
is exactly what guarantees the NFA has O(len(pattern)) states -- the
property that makes the simulation in matcher.py run in linear time instead
of blowing up exponentially like naive backtracking.
"""

import itertools

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

_id_counter = itertools.count()


class State:
    """A single NFA state / node.

    kind is one of:
      'char'         - consumes one character equal to self.c, then -> out
      'any'          - consumes any character except '\\n', then -> out
      'class'        - consumes one character matching self.charclass, -> out
      'epsilon'      - free (epsilon) transition to out, consumes nothing
      'split'        - free transition to *both* out and out1 (branch point)
      'assert_start' - zero-width assertion (^), then -> out
      'assert_end'   - zero-width assertion ($), then -> out
      'match'        - accepting state, terminal, no outgoing edges
    """

    __slots__ = ("id", "kind", "c", "charclass", "out", "out1")

    def __init__(self, kind):
        self.id = next(_id_counter)
        self.kind = kind
        self.c = None
        self.charclass = None
        self.out = None
        self.out1 = None

    def __repr__(self):  # pragma: no cover
        return f"State(id={self.id}, kind={self.kind!r})"


class Frag:
    """A partially-built NFA fragment: a start state and dangling patches.

    ``patches`` is a list of (state, attribute_name) pairs identifying
    out-pointers that still need to be connected to whatever comes next.
    """

    __slots__ = ("start", "patches")

    def __init__(self, start, patches):
        self.start = start
        self.patches = patches


def _patch(patches, target):
    for state, attr in patches:
        setattr(state, attr, target)


def _compile_node(node):
    if isinstance(node, Lit):
        s = State("char")
        s.c = node.c
        return Frag(s, [(s, "out")])

    if isinstance(node, Dot):
        s = State("any")
        return Frag(s, [(s, "out")])

    if isinstance(node, CharClassNode):
        s = State("class")
        s.charclass = node
        return Frag(s, [(s, "out")])

    if isinstance(node, Empty):
        s = State("epsilon")
        return Frag(s, [(s, "out")])

    if isinstance(node, StartAnchor):
        s = State("assert_start")
        return Frag(s, [(s, "out")])

    if isinstance(node, EndAnchor):
        s = State("assert_end")
        return Frag(s, [(s, "out")])

    if isinstance(node, Group):
        return _compile_node(node.node)

    if isinstance(node, Concat):
        frag = _compile_node(node.parts[0])
        for part in node.parts[1:]:
            nxt = _compile_node(part)
            _patch(frag.patches, nxt.start)
            frag = Frag(frag.start, nxt.patches)
        return frag

    if isinstance(node, Alt):
        frags = [_compile_node(b) for b in node.options]
        # Right-fold the branches into a chain of 'split' states so that
        # earlier branches always have higher match priority than later
        # ones (this is what gives us Perl/re-like leftmost-first
        # alternation semantics rather than POSIX leftmost-longest).
        result_start = frags[-1].start
        patches = list(frags[-1].patches)
        for f in reversed(frags[:-1]):
            s = State("split")
            s.out = f.start
            s.out1 = result_start
            result_start = s
            patches = f.patches + patches
        return Frag(result_start, patches)

    if isinstance(node, Star):
        inner = _compile_node(node.node)
        s = State("split")
        s.out = inner.start  # higher priority: try to loop again (greedy)
        _patch(inner.patches, s)
        return Frag(s, [(s, "out1")])

    if isinstance(node, Plus):
        inner = _compile_node(node.node)
        s = State("split")
        s.out = inner.start  # loop back into the body (greedy)
        _patch(inner.patches, s)
        return Frag(inner.start, [(s, "out1")])

    if isinstance(node, Optional):
        inner = _compile_node(node.node)
        s = State("split")
        s.out = inner.start  # higher priority: try to match (greedy)
        return Frag(s, inner.patches + [(s, "out1")])

    raise TypeError(f"Unknown AST node: {node!r}")  # pragma: no cover


def compile_to_nfa(ast):
    """Compile an AST into an NFA. Returns (start_state, match_state)."""
    frag = _compile_node(ast)
    match_state = State("match")
    _patch(frag.patches, match_state)
    return frag.start, match_state
