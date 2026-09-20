"""NFA simulation ("Pike's algorithm" / Thompson NFA simulation).

Rather than backtracking through the AST (which is what causes catastrophic
exponential blowup on patterns like ``(a*)*b``), we simulate *all* live NFA
states simultaneously, one input character at a time. At every text
position we keep a list of "threads" -- (nfa_state, match_start_position)
pairs -- ordered by match priority (leftmost start position first, then
"more greedy" / earlier alternation branch first). Each character advances
every thread at once, so the whole simulation is O(len(pattern) *
len(text)): linear in the length of the input text for a fixed pattern,
no matter how deeply nested the quantifiers are.

Priority order is preserved so that greedy quantifiers and left-to-right
alternation priority (`cat|dog` prefers `cat`) come out matching Python's
`re` module's leftmost-first backtracking semantics for the supported
(backreference-free, lookaround-free) subset of syntax -- this is exactly
what the cross-check tests in tests/test_regex_engine.py verify.

Algorithm sketch for one step at position ``pos``:
  1. Walk the current thread list in priority order. For each thread:
       - if it is sitting on the accepting ('match') state, record it as
         the best match ending at ``pos`` and stop looking at any *lower*
         priority threads this round (they can't beat this one);
       - otherwise (it's a char/any/class state) try to consume the
         character at ``pos`` and add its continuation to the next round's
         thread list.
  2. (search mode only) spawn a brand new lowest-priority thread starting
     at ``pos + 1``, so we don't need a separate O(n) outer loop to try
     every possible start position.
  3. Move to ``pos + 1`` with the new thread list, and repeat.

A thread reaching 'match' does not stop the whole simulation: a
higher-priority thread that is still alive (e.g. a greedy `a+` that could
still consume more) is allowed to keep running and, if it finishes later,
its result overwrites the earlier, shorter match -- which is exactly what
makes quantifiers greedy.
"""

from .nfa import compile_to_nfa


def _char_matches(state, ch):
    kind = state.kind
    if kind == "char":
        return state.c == ch
    if kind == "any":
        return ch != "\n"
    if kind == "class":
        return _class_matches(state.charclass, ch)
    return False


def _class_matches(cc, ch):
    in_class = ch in cc.chars or any(lo <= ch <= hi for lo, hi in cc.ranges)
    return (not in_class) if cc.negate else in_class


def _add_thread(state, start_pos, pos, text_len, threads, visited):
    """Epsilon-closure: follow free transitions, adding "real" (char-like or
    match) states to ``threads``. ``visited`` dedupes by state id so cyclic
    epsilon graphs (e.g. from ``(a*)*``) terminate in O(#states) instead of
    looping forever or blowing up -- this is the key to avoiding
    catastrophic backtracking.
    """
    if state is None or state.id in visited:
        return
    visited.add(state.id)
    kind = state.kind
    if kind == "split":
        _add_thread(state.out, start_pos, pos, text_len, threads, visited)
        _add_thread(state.out1, start_pos, pos, text_len, threads, visited)
    elif kind == "epsilon":
        _add_thread(state.out, start_pos, pos, text_len, threads, visited)
    elif kind == "assert_start":
        if pos == 0:
            _add_thread(state.out, start_pos, pos, text_len, threads, visited)
    elif kind == "assert_end":
        if pos == text_len:
            _add_thread(state.out, start_pos, pos, text_len, threads, visited)
    else:  # 'char', 'any', 'class', 'match'
        threads.append((state, start_pos))


class MatchObject:
    """Minimal stand-in for re.Match, covering what we need."""

    __slots__ = ("string", "_start", "_end")

    def __init__(self, string, start, end):
        self.string = string
        self._start = start
        self._end = end

    def group(self):
        return self.string[self._start:self._end]

    def span(self):
        return (self._start, self._end)

    def start(self):
        return self._start

    def end(self):
        return self._end

    def __eq__(self, other):
        if not isinstance(other, MatchObject):
            return NotImplemented
        return self.string == other.string and self.span() == other.span()

    def __repr__(self):
        return f"<MatchObject span={self.span()} match={self.group()!r}>"


class CompiledRegex:
    """A compiled pattern, returned by ``regex_engine.compile``."""

    def __init__(self, pattern, ast, start_state, match_state):
        self.pattern = pattern
        self.ast = ast
        self._start_state = start_state
        self._match_state_id = match_state.id

    def match(self, text):
        """Like re.match: try to match starting exactly at position 0."""
        return self._run(text, search_mode=False, start_pos=0)

    def search(self, text):
        """Like re.search: find the leftmost match anywhere in text."""
        return self._run(text, search_mode=True, start_pos=0)

    def findall(self, text):
        """Like re.findall: all non-overlapping matches, left to right."""
        results = []
        pos = 0
        n = len(text)
        while pos <= n:
            m = self._run(text, search_mode=True, start_pos=pos)
            if m is None:
                break
            s, e = m.span()
            results.append(text[s:e])
            pos = e + 1 if e == s else e
        return results

    # -- core simulation -----------------------------------------------------

    def _run(self, text, search_mode, start_pos):
        n = len(text)
        clist = []
        visited = set()
        _add_thread(self._start_state, start_pos, start_pos, n, clist, visited)

        pos = start_pos
        matched = None

        while True:
            nlist = []
            visited2 = set()

            for state, sp in clist:
                if state.id == self._match_state_id:
                    matched = (sp, pos)
                    break  # discard remaining lower-priority threads
                if pos < n and _char_matches(state, text[pos]):
                    _add_thread(state.out, sp, pos + 1, n, nlist, visited2)

            # Only spawn a fresh (necessarily lower-priority, later-starting)
            # thread while no match has been found yet. Once some thread
            # has matched, every remaining/older thread still alive in
            # nlist is by construction *higher* priority than that match
            # (it survived being placed before the match in list order),
            # so it's still allowed to overwrite `matched` with a better
            # result later -- but a newly spawned thread would only ever
            # start at a later, strictly worse position, so admitting it
            # after a match is already found could incorrectly clobber a
            # correct leftmost match with a later one.
            if search_mode and pos < n and matched is None:
                _add_thread(
                    self._start_state, pos + 1, pos + 1, n, nlist, visited2
                )

            if pos >= n:
                break
            if not nlist:
                break

            clist = nlist
            pos += 1

        if matched is None:
            return None
        return MatchObject(text, matched[0], matched[1])
