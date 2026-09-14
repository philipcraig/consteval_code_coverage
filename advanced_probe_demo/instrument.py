#!/usr/bin/env python3
"""
Insert consteval coverage traps into a copy of a C++ header.

Usage: instrument.py <header>     prints the instrumented copy to stdout

A scanner, not a parser: it tracks strings, comments, brace depth and
`consteval` regions, and inserts `probe::trap<__LINE__>();` at the start of
every block and before every `return` and `throw` inside consteval code.
Every insertion stays on its original line, so the copy has the same line
numbers as the original and `__LINE__` identifies the probe point.
Constructs it does not recognise are left alone: that under-measures but
never miscompiles, and probe.py reports a compile that fails with no trap
fired as an instrumenter bug.
"""

import sys

TRAP = "probe::trap<__LINE__>();"

# Tokens whose presence directly before `{` marks it as opening a compound
# statement rather than a braced initialiser: `)` ends a control clause,
# function signature or lambda; `consteval` opens a consteval block.
BLOCK_OPEN = {")", "else", "try", "do", "consteval"}

# Tokens after which a `return` or `throw` token starts a statement.
STATEMENT_START = {";", "{", "}", ")", ":", "else", "do"}


class Instrumenter:
    def __init__(self) -> None:
        self.brace_depth = 0
        self.paren_depth = 0
        self.regions: list[int] = []  # brace depth of each open consteval region
        self.pending_consteval = False  # next block-opening `{` starts a region
        self.skip_next_block = False  # a switch body: nothing before its first case runs
        self.in_block_comment = False
        self.last_token = ""
        self.wrapping: int | None = None  # nesting while wrapping `return ...;`
        self.probe_lines: list[int] = []

    def instrument(self, lines: list[str]) -> list[str]:
        return [self._line(text, number) for number, text in enumerate(lines, 1)]

    def _in_region(self) -> bool:
        return bool(self.regions)

    def _record(self, number: int) -> None:
        if not self.probe_lines or self.probe_lines[-1] != number:
            self.probe_lines.append(number)

    def _line(self, line: str, number: int) -> str:
        if not self.in_block_comment and line.lstrip().startswith("#"):
            return line
        out: list[str] = []
        i = 0
        while i < len(line):
            if self.in_block_comment:
                end = line.find("*/", i)
                if end == -1:
                    out.append(line[i:])
                    break
                out.append(line[i : end + 2])
                i = end + 2
                self.in_block_comment = False
                continue
            c = line[i]
            if c.isalpha() or c == "_":
                end = i + 1
                while end < len(line) and (line[end].isalnum() or line[end] == "_"):
                    end += 1
                out.append(self._token(line[i:end], number))
                i = end
                continue
            if line.startswith("//", i):
                out.append(line[i:])
                break
            if line.startswith("/*", i):
                out.append("/*")
                i += 2
                self.in_block_comment = True
                continue
            after_identifier = i > 0 and (line[i - 1].isalnum() or line[i - 1] == "_")
            if c == '"' or (c == "'" and not after_identifier):  # not a digit separator
                end = self._literal_end(line, i, c)
                out.append(line[i:end])
                i = end
                continue
            out.append(self._punctuation(c, number))
            i += 1
        return "".join(out)

    @staticmethod
    def _literal_end(line: str, start: int, quote: str) -> int:
        i = start + 1
        while i < len(line):
            if line[i] == "\\":
                i += 2
                continue
            if line[i] == quote:
                return i + 1
            i += 1
        return i

    def _token(self, token: str, number: int) -> str:
        prefix = ""
        if token == "consteval" and self.wrapping is None:
            self.pending_consteval = True
        elif token == "switch":
            self.skip_next_block = True
        elif (
            token in ("return", "throw")
            and self._in_region()
            and self.wrapping is None
            and self.last_token in STATEMENT_START
        ):
            self._record(number)
            prefix = "{ " + TRAP + " "
            self.wrapping = 0
        self.last_token = token
        return prefix + token

    def _punctuation(self, c: str, number: int) -> str:
        if c == "{":
            return self._open_brace(number)
        if c == "}":
            self._close_brace()
            self.last_token = "}"
            return "}"
        if c in "([":
            self.paren_depth += 1
            if self.wrapping is not None:
                self.wrapping += 1
        elif c in ")]":
            self.paren_depth -= 1
            if self.wrapping is not None:
                self.wrapping -= 1
        elif c == ";":
            if self.wrapping == 0:
                self.wrapping = None
                self.last_token = ";"
                return "; }"
            if self.paren_depth == 0 and self.brace_depth == 0:
                # A declaration ended before any body opened: a forward
                # declaration cannot start a consteval region.
                self.pending_consteval = False
        if not c.isspace():
            self.last_token = c
        return c

    def _open_brace(self, number: int) -> str:
        self.brace_depth += 1
        opens_block = self.last_token in BLOCK_OPEN
        if self.pending_consteval and opens_block:
            self.regions.append(self.brace_depth)
            self.pending_consteval = False
        if opens_block and self.skip_next_block:
            self.skip_next_block = False
            self.last_token = "{"
            return "{"
        if self._in_region() and opens_block:
            self._record(number)
            # `;` so that a `return` following on the same line still counts
            # as starting a statement.
            self.last_token = ";"
            return "{ " + TRAP
        self.last_token = "{"
        return "{"

    def _close_brace(self) -> None:
        if self.regions and self.brace_depth == self.regions[-1]:
            self.regions.pop()
        self.brace_depth -= 1


def instrument(source: str) -> tuple[str, list[int]]:
    """Return the instrumented copy of `source` and its probe point lines."""
    instrumenter = Instrumenter()
    lines = instrumenter.instrument(source.splitlines())
    return "\n".join(lines) + "\n", instrumenter.probe_lines


if __name__ == "__main__":
    with open(sys.argv[1]) as header:
        sys.stdout.write(instrument(header.read())[0])
