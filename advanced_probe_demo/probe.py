#!/usr/bin/env python3
"""
Consteval coverage by compile-time trap probing, in batched, parallel rounds.

Usage: probe.py [--jobs N] [--compiler CXX] <header> <test file>...

The header is instrumented into a scratch directory (see instrument.py),
and every trap in that copy is a probe point. Each round arms every probe
point not yet known to be covered, splits the armed set into up to N
interleaved batches, compiles the test file once per batch with
-fsyntax-only, and collects the trap keys from the compiler's diagnostics.
A trap that always runs after another armed trap of the same batch in the
same constant evaluation is masked this round and surfaces in a later one,
once the earlier trap is disarmed. Rounds stop when one finds nothing new.
With several test files, each is probed in turn and arms only what the
earlier ones left uncovered, so list them cheapest to compile first.
"""

import argparse
import concurrent.futures
import itertools
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from instrument import instrument

# With constexpr exceptions (GCC 16+) the diagnostic names the thrown
# `trap_hit<N>`; without them the throw is merely "not a constant
# expression" and the note chain names the failing `trap<N>()` instead
# (GCC prints `probe::trap<15>()`, Clang `trap<15L>()`).
HIT = re.compile(r"\btrap_hit<(\d+)L?>|\btrap<(\d+)L?>\(\)")


def armed_header(armed: frozenset[int]) -> str:
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


def batches(armed: set[int], count: int) -> list[frozenset[int]]:
    """Split `armed` into up to `count` interleaved batches.

    Consecutive probe points usually lie on the same evaluation path, where
    the first to run masks the rest, so neighbours go to different batches.
    """
    ordered = sorted(armed)
    count = max(1, min(count, len(ordered)))
    return [frozenset(ordered[start::count]) for start in range(count)]


def compile_batch(
    compiler: str, work: Path, unit: str, index: int, armed: frozenset[int]
) -> set[int]:
    """Compile `unit` with `armed` armed and return the keys that fired."""
    trap_header = work / f"{unit}.{index}.armed.h"
    trap_header.write_text(armed_header(armed))
    result = subprocess.run(
        [compiler, "-std=c++23", "-fsyntax-only", "-w", "-include",
         str(trap_header), str(work / unit)],
        capture_output=True, text=True,
    )
    hits = {int(a or b) for a, b in HIT.findall(result.stderr)} & armed
    if result.returncode != 0 and not hits:
        sys.exit(f"{unit} failed to compile with no trap fired:\n{result.stderr}")
    return hits


def probe(compiler: str, work: Path, unit: str, candidates: set[int], jobs: int) -> set[int]:
    """Return the subset of `candidates` that compiling `unit` evaluates."""
    covered: set[int] = set()
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        for round_number in itertools.count(1):
            armed = candidates - covered
            if not armed:
                break
            split = batches(armed, jobs)
            compiles = [
                pool.submit(compile_batch, compiler, work, unit, i, batch)
                for i, batch in enumerate(split)
            ]
            hits: set[int] = set()
            for done in concurrent.futures.as_completed(compiles):
                hits |= done.result()
            how = f" in {len(split)} batches" if len(split) > 1 else ""
            print(f"{unit} round {round_number}: {len(armed)} armed{how}, {len(hits)} hit")
            if not hits:
                break
            covered |= hits
    return covered


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    parser.add_argument("--jobs", type=int, default=1, help="compiles per round")
    parser.add_argument("--compiler", default="g++")
    parser.add_argument("header", type=Path)
    parser.add_argument("units", nargs="+", type=Path, metavar="test-file")
    arguments = parser.parse_args()

    source = arguments.header.read_text()
    instrumented, points = instrument(source)
    print(f"{len(points)} probe points in {arguments.header.name}")

    covered: set[int] = set()
    with tempfile.TemporaryDirectory() as scratch:
        work = Path(scratch)
        (work / arguments.header.name).write_text(instrumented)
        for unit in arguments.units:
            shutil.copy(unit, work)
            covered |= probe(
                arguments.compiler, work, unit.name, set(points) - covered, arguments.jobs
            )

    lines = source.splitlines()
    for line in points:
        mark = "covered  " if line in covered else "UNCOVERED"
        print(f"  {mark} {arguments.header.name}:{line:<3} {lines[line - 1].strip()}")
    print(f"{len(covered)}/{len(points)} probe points evaluated")


if __name__ == "__main__":
    main()
