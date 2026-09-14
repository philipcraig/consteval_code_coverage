#!/usr/bin/env python3
"""
Consteval coverage by compile-time trap probing, batched into rounds.

Usage: probe.py <instrumented header> <test translation unit> [compiler]

Every line of the header that calls `probe::trap<__LINE__>()` is a probe
point. Each round arms every probe point not yet known to be covered,
compiles the translation unit once with -fsyntax-only, and collects the
`trap_hit<N>` names from the compiler's uncaught-exception diagnostics.
A trap that always runs after another armed trap in the same constant
evaluation is masked this round and surfaces in a later one, once the
earlier trap is disarmed. Rounds stop when one finds nothing new.
"""

import re
import subprocess
import sys
import tempfile
from pathlib import Path

# With constexpr exceptions (GCC 16+) the diagnostic names the thrown
# `trap_hit<N>`; without them the throw is merely "not a constant
# expression" and the note chain names the failing `trap<N>()` instead
# (GCC prints `probe::trap<15>()`, Clang `trap<15L>()`).
HIT = re.compile(r"\btrap_hit<(\d+)L?>|\btrap<(\d+)L?>\(\)")


def armed_header(armed: set[int]) -> str:
    specializations = "\n".join(
        f"template <> constexpr bool armed<{line}> = true;" for line in sorted(armed)
    )
    return f"""\
namespace probe {{
template <long Line> struct trap_hit {{}};      // not a std::exception
template <long Line> constexpr bool armed = false;
{specializations}
template <long Line> constexpr void trap() {{
  if consteval {{
    if constexpr (armed<Line>) throw trap_hit<Line>{{}};
  }}
}}
}}  // namespace probe
"""


def main() -> None:
    header, unit = Path(sys.argv[1]), Path(sys.argv[2])
    compiler = sys.argv[3] if len(sys.argv) > 3 else "g++"
    lines = header.read_text().splitlines()
    points = {
        n
        for n, text in enumerate(lines, 1)
        if "probe::trap<__LINE__>" in text and not text.lstrip().startswith("//")
    }
    covered: set[int] = set()

    with tempfile.TemporaryDirectory() as work:
        armed_path = Path(work, "armed.h")
        for round_number in range(1, len(points) + 2):
            armed = points - covered
            if not armed:
                break
            armed_path.write_text(armed_header(armed))
            result = subprocess.run(
                [compiler, "-std=c++23", "-fsyntax-only", "-w", "-include",
                 str(armed_path), "-I", str(header.parent), str(unit)],
                capture_output=True, text=True,
            )
            hits = {int(a or b) for a, b in HIT.findall(result.stderr)} & armed
            if result.returncode != 0 and not hits:
                sys.exit(f"compile failed with no trap fired:\n{result.stderr}")
            print(f"round {round_number}: {len(armed)} armed, {len(hits)} hit")
            if not hits:
                break
            covered |= hits

    for line in sorted(points):
        mark = "covered  " if line in covered else "UNCOVERED"
        print(f"  {mark} {header.name}:{line:<3} {lines[line - 1].strip()}")
    print(f"{len(covered)}/{len(points)} probe points evaluated")


if __name__ == "__main__":
    main()
