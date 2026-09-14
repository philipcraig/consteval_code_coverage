# Consteval code coverage

runtime code-coverage tools cannot see `consteval` code, because it never runs.
This repository shows a technique that measures it anyway: instrument the
compile-time code with traps that throw during constant evaluation when
armed, arm every untested trap at once, read the compiler's error output
to see which ones fired, and repeat with those disarmed until nothing new
fires. The write-up is in [post.md](post.md).

There are two demonstrations of the same small `consteval` name-mangler
and the same deliberately incomplete test suite:

- `basic_trap_demo/` shows the mechanism with nothing in the way. The
  traps are placed by hand in `mangle.hh`, and `probe.py` runs the rounds
  with one compile each.
- `advanced_probe_demo/` shows the tooling. Its `mangle.hh` has no traps in
  it: `instrument.py` inserts them into a copy in a scratch directory, and
  `probe.py` splits each round into interleaved batches compiled in
  parallel and takes several test files, cheapest first.

## Try it

```
./run.sh            # uses g++, or set CXX
CXX=clang++ ./run.sh
```

`run.sh` runs both demos. For the basic one it checks that the
instrumented header compiles with no trap armed, then probes; expected
output ends with:

```
round 7: 4 armed, 0 hit
  ...
  UNCOVERED mangle.hh:18  probe::trap<__LINE__>();
  UNCOVERED mangle.hh:20  probe::trap<__LINE__>(); return out;
  UNCOVERED mangle.hh:44  probe::trap<__LINE__>();
  UNCOVERED mangle.hh:45  probe::trap<__LINE__>(); throw "division by zero in mangle_ratio";
8/12 probe points evaluated
```

For the advanced one it prints the twelve lines `instrument.py` changes,
then probes once serially, which reproduces the seven rounds above from
the clean header, and once with `--jobs 4`:

```
12 probe points in mangle.hh
mangle_test.cc round 1: 12 armed in 4 batches, 5 hit
mangle_test.cc round 2: 7 armed in 4 batches, 2 hit
mangle_test.cc round 3: 5 armed in 4 batches, 1 hit
mangle_test.cc round 4: 4 armed in 4 batches, 0 hit
  ...
  UNCOVERED mangle.hh:16  if (value == 0) {
  UNCOVERED mangle.hh:18  return out;
  ...
  UNCOVERED mangle.hh:37  if (denominator == 0) {
  UNCOVERED mangle.hh:38  throw "division by zero in mangle_ratio";
  ...
8/12 probe points evaluated
```

Striping the armed set across batches keeps a function's entry trap from
masking the traps behind it, so four rounds replace seven.

Add `static_assert(view(mangle_decimal(0)) == "0");` to either
`mangle_test.cc` and run it again to watch two of them turn green.

Requires Python 3.10 or later and a C++23 compiler: GCC 15, GCC trunk and
a recent Clang all give the output above. With C++26 constexpr exceptions
the compiler names the thrown `trap_hit<N>`; without them the note chain
names the failing `trap<N>()`, and `probe.py` reads either.

## Files

`basic_trap_demo/`:

- `mangle.hh`: a small `consteval` name-mangler with hand-placed traps at
  every block entry and before every `return` and `throw`.
- `mangle_test.cc`: the test suite, which deliberately leaves the zero
  branch and the division-by-zero throw untested.
- `probe.py`: the batched-round prober, about 70 lines, one compile per
  round.
- `unarmed.h`: a trap header with nothing armed, for ordinary builds of
  the instrumented header.

`advanced_probe_demo/`:

- `mangle.hh`: the same mangler with no traps in it.
- `mangle_test.cc`: the same test suite.
- `instrument.py`: the instrumenter, about 180 lines. A scanner that
  tracks strings, comments, brace depth and `consteval` regions and
  inserts a trap at every block entry and before every `return` and
  `throw`, keeping every insertion on its original line. Run it on a
  header to print the instrumented copy.
- `probe.py`: the prober, about 140 lines. Instruments the header into a
  scratch directory, runs the rounds with up to `--jobs` interleaved
  batches compiled in parallel, and probes each test file in turn,
  arming only what the earlier ones left uncovered. `--lcov-output`
  also writes the result as an LCOV trace.

`run.sh` runs both; `post.md` is the article explaining the technique and
why arming many traps in one compile is sound; `NOTES.md` records how the
numbers in the post were measured.
