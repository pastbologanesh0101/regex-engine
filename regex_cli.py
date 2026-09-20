#!/usr/bin/env python3
"""Command-line front end for regex_engine.

Usage:
    python regex_cli.py '<pattern>' '<test string>'

Example:
    $ python regex_cli.py '(ab|cd)+' 'xxabcdcdyy'
    Pattern: '(ab|cd)+'
    String:  'xxabcdcdyy'
    match():   NO MATCH
    search():  MATCH  span=(2, 8) matched='abcdcd'
    findall(): ['abcdcd']
"""

import sys

import regex_engine


def main(argv):
    if len(argv) != 3:
        print("Usage: python regex_cli.py '<pattern>' '<test string>'")
        return 1

    pattern, text = argv[1], argv[2]

    try:
        rx = regex_engine.compile(pattern)
    except regex_engine.RegexSyntaxError as exc:
        print(f"Error: invalid pattern: {exc}")
        return 1

    print(f"Pattern: {pattern!r}")
    print(f"String:  {text!r}")

    m = rx.match(text)
    if m:
        print(f"match():   MATCH  span={m.span()} matched={m.group()!r}")
    else:
        print("match():   NO MATCH")

    s = rx.search(text)
    if s:
        print(f"search():  MATCH  span={s.span()} matched={s.group()!r}")
    else:
        print("search():  NO MATCH")

    print(f"findall(): {rx.findall(text)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
