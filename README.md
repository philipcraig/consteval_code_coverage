# Consteval code coverage

Runtime coverage tools cannot see `consteval` code, because it never runs.
This repository shows a technique that measures it anyway: instrument the
compile-time code with traps that throw during constant evaluation when
armed, arm every untested trap at once, read the compiler's error output
to see which ones fired, and repeat with those disarmed until nothing new
fires. The write-up is in [post.md](post.md).

## Try it

```
./run.sh            # uses g++, or set CXX
CXX=clang++ ./run.sh
```

`run.sh` checks that the instrumented demo compiles with no trap armed,
then runs the probe and prints which probe points the test suite never
evaluated. Expected output ends with:

```
round 7: 4 armed, 0 hit
  ...
  UNCOVERED mangle.hh:18  probe::trap<__LINE__>();
  UNCOVERED mangle.hh:20  probe::trap<__LINE__>(); return out;
  UNCOVERED mangle.hh:44  probe::trap<__LINE__>();
  UNCOVERED mangle.hh:45  probe::trap<__LINE__>(); throw "division by zero in mangle_ratio";
8/12 probe points evaluated
```

Add `static_assert(view(mangle_decimal(0)) == "0");` to
`demo/mangle_test.cc` and run it again to watch two of them turn green.

Requires Python 3 and a C++23 compiler: GCC 15, GCC trunk and a recent
Clang all give the output above. With C++26 constexpr exceptions the compiler names the
thrown `trap_hit<N>`; without them the note chain names the failing
`trap<N>()`, and `probe.py` reads either.

## Files

- `demo/mangle.hh`: a small `consteval` name-mangler with hand-placed
  traps at every block entry and before every `return` and `throw`.
- `demo/mangle_test.cc`: the test suite, which deliberately leaves the zero
  branch and the division-by-zero throw untested.
- `demo/probe.py`: the batched-round prober, about 70 lines.
- `demo/unarmed.h`: a trap header with nothing armed, for ordinary builds
  of the instrumented header.
- `run.sh`: unarmed compile check, then the probe.
- `post.md`: the article explaining the technique and why arming many
  traps in one compile is sound.
- `NOTES.md`: how the numbers in the post were measured, and publishing
  notes.

In real use the traps are inserted by an instrumenter into a copy of each
header, keyed on header index as well as line, and the prober runs the
rounds per test translation unit, cheapest first. The demo keeps the traps
hand-placed so the mechanism is visible.
