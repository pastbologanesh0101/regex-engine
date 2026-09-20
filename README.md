# Regex Engine

[![tests](https://github.com/pastbologanesh0101/regex-engine/actions/workflows/tests.yml/badge.svg)](https://github.com/pastbologanesh0101/regex-engine/actions/workflows/tests.yml)

A regular expression engine built entirely from scratch in pure Python
(standard library only). No use of Python's built-in `re` module anywhere
in the implementation — `re` appears exactly once in the whole project, in
the test suite, purely as a reference oracle to cross-check this engine's
answers against.

It implements the three classic pieces of a real regex engine:

1. A **hand-written recursive-descent parser** that turns a pattern string
   into an AST.
2. A **compiler that builds an NFA from the AST using Thompson's
   construction** (the textbook McNaughton-Yamada-Thompson algorithm).
3. A **linear-time NFA simulator** (Pike's algorithm / "Thompson NFA
   simulation") that runs all possible match states simultaneously instead
   of backtracking — so pathological patterns that make naive regex
   engines hang for years (`(a*)*b` against a long run of `a`s) finish in
   milliseconds here.

## Supported syntax

| Syntax        | Meaning                                             |
|---------------|------------------------------------------------------|
| `abc`         | literal characters, concatenated                     |
| `\|`          | alternation, e.g. `cat\|dog`                          |
| `*`           | zero or more of the preceding atom (greedy)          |
| `+`           | one or more of the preceding atom (greedy)           |
| `?`           | zero or one of the preceding atom (greedy)           |
| `(...)`       | grouping (for precedence; not a capturing group)     |
| `[abc]`       | character class: matches `a`, `b`, or `c`            |
| `[a-z]`       | character class range                                 |
| `[^abc]`      | negated character class                              |
| `.`           | any character except newline                         |
| `^`           | zero-width assertion: only matches at position 0     |
| `$`           | zero-width assertion: only matches at end of string  |
| `\x`          | escapes any character `x` (use for literal `. * + ? ( ) [ ] | ^ $ \`) |

Quantifiers bind tightest, then concatenation, then alternation — the same
precedence as every mainstream regex flavor, e.g. `ab*|c` means
`(a(b*))|(c)`.

**Not supported** (kept out on purpose to keep the engine's scope honest):
counted repetition `{m,n}`, shorthand classes `\d \w \s`, non-greedy
quantifiers `*?`, capturing-group backreferences, and lookaround. `(...)`
groups only affect grouping/precedence, not capturing — `findall` and
friends always return the *whole* match.

Two behaviors intentionally mirror Python's `re` defaults so the
cross-check tests are meaningful: `.` does not match `\n`, and `^`/`$`
anchor to the absolute start/end of the string (no multiline mode).

## How it works

### 1. Parsing → AST

`regex_engine/parser.py` implements a standard recursive-descent parser
over this grammar (highest precedence first):

```
Alt      := Concat ('|' Concat)*
Concat   := Repeat*
Repeat   := Atom ('*' | '+' | '?')?
Atom     := Literal | '.' | '(' Alt ')' | CharClass | '^' | '$' | '\' Literal
```

Each rule is one method (`_parse_alt`, `_parse_concat`, `_parse_repeat`,
`_parse_atom`), and each produces a small AST node from
`regex_engine/ast_nodes.py` (`Lit`, `Concat`, `Alt`, `Star`, `Plus`,
`Optional`, `Group`, `CharClassNode`, `Dot`, `StartAnchor`, `EndAnchor`).

### 2. AST → NFA via Thompson's construction

`regex_engine/nfa.py` walks the AST and builds an NFA out of small
*fragments*. A fragment is a start state plus a list of still-dangling
("unpatched") out-pointers. The classic Thompson construction rules:

- **Literal / `.` / class**: one state that consumes a character, with one
  dangling out-pointer.
- **Concatenation `AB`**: patch `A`'s dangling pointers to `B`'s start
  state; the result's dangling pointers are `B`'s.
- **Alternation `A|B`**: a new `split` state with epsilon-edges to both
  `A`'s and `B`'s start states; dangling pointers are the union of both.
  Branches are tried in left-to-right order (`split.out` before
  `split.out1`), which is what gives `cat|dog`-style *leftmost-branch
  priority* instead of POSIX longest-match ambiguity.
- **Star `A*`**: a `split` state whose first edge re-enters `A` (loop) and
  whose second edge is the fragment's new dangling exit; `A`'s own
  dangling pointers are patched back into the `split` state, forming the
  loop.
- **Plus `A+`**: `A` runs once unconditionally, then a `split` state either
  loops back into `A` or exits.
- **Optional `A?`**: a `split` state that either enters `A` or jumps
  straight to the exit; both paths converge at the same dangling pointers.

Every state has at most two outgoing edges, so an NFA for a pattern of
length *p* has O(*p*) states — this bound is exactly what keeps the
simulation below linear-time-per-character instead of exponential.

### 3. Simulating the NFA (no backtracking)

`regex_engine/matcher.py` implements Pike's algorithm: instead of trying
one path through the NFA and backtracking on failure (what a naive regex
engine — and what a naive recursive-descent *matcher*, as opposed to
parser — would do), it tracks the entire *set* of NFA states that are
simultaneously reachable after consuming each character, and advances all
of them at once ("simultaneous state-set simulation").

Concretely, at every text position we keep a priority-ordered list of
threads (`(state, match_start_position)` pairs). Advancing one character:

1. Walk the thread list in priority order. A thread sitting on the
   accepting state records a candidate match and causes every
   *lower*-priority thread in this round to be discarded (they can't beat
   it). Threads before it in the list were already processed and their
   continuations survive — those are strictly higher priority, so they're
   still allowed to later produce a *better* (typically longer / greedier)
   match that overwrites this one.
2. Every surviving thread tries to consume the current character and
   contributes its continuation to next round's thread list.
3. In search mode, one brand-new lowest-priority thread is spawned at the
   next position (but only while no match has been found yet — once
   something has matched, any newly spawned thread would necessarily start
   later, i.e. be strictly worse by "leftmost" priority, so admitting it
   could only ever *wrongly* clobber a correct earlier match).

Thread-list order encodes exactly the priority we want: earlier start
position beats later start position, and within the same start position,
"try to consume more" (loop) beats "exit" for `*`/`+`, and left branch
beats right branch for `|` — together this reproduces Perl/`re`-style
*leftmost-first* semantics (not POSIX leftmost-longest) for the
backreference-free subset of syntax we support.

Epsilon-closures (following `split`/anchor edges) are deduplicated by
state id within each step, so cyclic epsilon graphs — which do arise, e.g.
from `(a*)*` — terminate in O(states) work instead of looping or
exploding. Combined with the O(pattern length) state count from Thompson's
construction, one full run of `match`/`search` is **O(len(pattern) ×
len(text))**: linear in the input text for a fixed pattern, regardless of
how deeply nested the quantifiers are. That is the whole reason patterns
like `(a*)*b` cannot cause catastrophic backtracking here — there is no
backtracking to begin with.

### API

```python
import regex_engine

rx = regex_engine.compile(r"(ab|cd)+")

rx.match("abcdab")       # MatchObject, anchored at position 0
rx.search("xxabcdxx")    # MatchObject, found anywhere in the string
rx.findall("ababcdcd")   # ['ababcdcd'] -- non-overlapping matches

m = rx.search("xxabcdxx")
m.span()    # (2, 8)
m.group()   # 'abcd'
m.start()   # 2
m.end()     # 8
```

`compile`, `match`, `search`, and `findall` intentionally mirror the shape
of Python's `re` module so it's a drop-in-feeling mental model, but every
byte of matching logic is ours.

### CLI

```
python regex_cli.py '<pattern>' '<test string>'
```

Example:

```
$ python regex_cli.py '(ab|cd)+' 'xxabcdcdyy'
Pattern: '(ab|cd)+'
String:  'xxabcdcdyy'
match():   NO MATCH
search():  MATCH  span=(2, 8) matched='abcdcd'
findall(): ['abcdcd']
```

## Running the tests

```
python -m unittest discover -s tests -v
# or, if you have pytest installed:
python -m pytest tests/ -v
```

The test suite (`tests/test_regex_engine.py`) covers:

- literal matching, concatenation, alternation, `*`, `+`, `?`, grouping
  with alternation inside (`(ab|cd)+`), character classes (`[a-z]`,
  `[^0-9]`), the wildcard `.`, and anchors `^`/`$`;
- `findall` returning all correct non-overlapping matches;
- a **pathological-pattern timing test**: `(a*)*b` and `(a+)+c` against
  thousands of `a`s with no trailing terminator, asserting the search
  completes in a couple of seconds — proof this is a real NFA simulation
  and not exponential backtracking in disguise;
- a **cross-check suite against Python's real `re` module** over dozens of
  pattern/string pairs, asserting `match()`, `search()`, and `findall()`
  agree exactly with `re`'s output — the strongest correctness evidence
  a hand-rolled engine like this can produce.

A GitHub Actions workflow (`.github/workflows/tests.yml`) runs the full
suite on push and pull request against Python 3.11 and 3.12.

## Project layout

```
regex_engine/
  ast_nodes.py   # AST node classes (pure data)
  parser.py      # recursive-descent parser: pattern string -> AST
  nfa.py         # Thompson's construction: AST -> NFA
  matcher.py     # NFA simulation (Pike's algorithm) + public Compiled API
  __init__.py    # regex_engine.compile(...)
regex_cli.py     # command-line front end
tests/
  test_regex_engine.py
```

## License

MIT — see [LICENSE](LICENSE).
