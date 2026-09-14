# Coverage for code that never runs: trap probing for consteval C++

Runtime coverage tools cannot see `consteval` code, because it never runs. Here is a way to measure it anyway, using the one side effect a constant evaluation is allowed to have: it can fail the build.

## The gap

If you have written any serious compile-time code lately, you have some `consteval` functions. Perhaps they walk a reflection of a class and generate a vtable. Perhaps they mangle a type name, or validate a format string, or build a lookup table. They are real code, with branches and loops and error paths, and they deserve real tests.

The tests are easy enough to write: a `static_assert`, a template instantiated with the interesting arguments, a `consteval` block that checks a result. What you cannot easily get is a coverage report. Runtime instrumentation, `gcc --coverage` and `llvm-cov` alike, works by compiling counters into the generated code and reading them back after the program runs. A `consteval` function generates no code. gcov marks every line of it as non-executable, so a `consteval` function that no test touches is indistinguishable, in the report, from one that is tested to death.

For `constexpr` code there is a well-known dodge: run every test at run time as well as at compile time, and let runtime instrumentation observe the runtime pass. That does not work for `consteval`. An immediate function cannot be called at run time at all, and once you call a reflection metafunction from a function, that function has to be immediate too. The whole point of the code is that it only exists inside the compiler.

So the question is: how do you observe what the constant evaluator did?

## The one bit that escapes

A constant evaluation is designed to be hermetic. Nothing it does leaks out. It cannot write a file, print a line, or increment a counter that survives it. There is exactly one thing it can do that the outside world notices: it can fail, and a failed constant evaluation in a context that requires a constant is a compile error.

One bit per evaluation. It turns out that is enough.

The idea is to instrument the `consteval` code with traps. A trap is a call inserted at the start of every block and before every `return` and `throw`. Each trap is keyed by its location. Unarmed, a trap does nothing. Armed, it throws during constant evaluation, the evaluation fails, and the compiler reports an error that names the trap. Compile the test suite with a trap armed and see whether the build fails. If it did, the test suite evaluated that line. If it compiled cleanly, nothing in the test suite ever reached it.

Everything about that is standard C++. The instrumented copy of the header compiles under `-fsyntax-only`, because constant evaluation happens during semantic analysis, so you never even generate an object file.

## The trap

Here is the whole runtime side of the mechanism, in a header that is force-included ahead of everything else with `-include`:

```cpp
namespace probe {

// Not derived from std::exception, so no typed catch in the code under
// test can swallow it.
template <long Line> struct trap_hit {};

template <long Line> constexpr bool armed = false;
template <> constexpr bool armed<15> = true;   // generated per compile
template <> constexpr bool armed<42> = true;

template <long Line> constexpr void trap() {
  if consteval {
    if constexpr (armed<Line>) throw trap_hit<Line>{};
  }
}

}  // namespace probe
```

And here is what an instrumented function looks like, with the traps spread onto their own lines so you can see them. The real instrumenter only ever inserts text within a line, so line numbers in the copy match the original, and `__LINE__` is the key:

```cpp
consteval digits mangle_decimal(long long value) {
  probe::trap<__LINE__>();
  digits out;
  if (value == 0) {
    probe::trap<__LINE__>();
    out.push('0');
    probe::trap<__LINE__>(); return out;
  }
  if (value < 0) {
    probe::trap<__LINE__>();
    out.push('n');
    value = -value;
  }
  // ...
  probe::trap<__LINE__>(); return out;
}
```

Three details are doing more work than they look.

The key is a template argument, not a value. GCC's diagnostic for an uncaught exception during constant evaluation prints the type of the exception, so `trap_hit<15>` appears in the error text as plain digits inside angle brackets, whatever the locale does to the quotation marks around it. A value carried in a struct field is printed inside braces with locale-dependent punctuation, and I lost an afternoon to a regex that silently matched nothing because the compiler had switched to typographic quotes.

The armed set is a variable template with explicit specializations, tested with `if constexpr`. An unarmed trap's body is empty after instantiation. It costs the constant evaluator nothing, which matters when the code under test is a name-mangling loop that calls a trap a few thousand times per evaluation.

The exception type is not derived from `std::exception`. Constant-evaluated code can have `catch` blocks, and a `catch (const std::exception&)` in the code under test would swallow the trap and mask everything beneath it. A `catch (...)` still would, so grep for those first.

The compiler side is undemanding. With constexpr exceptions, which are C++26 and shipped in GCC 16, the diagnostic is "uncaught exception 'probe::trap_hit<15>()'". Without them, on GCC 15 or Clang, the `throw` is simply not a constant expression, but the note chain that follows the error names the call that failed: "in 'constexpr' expansion of 'probe::trap<15>()'" on GCC, "in call to 'trap<15L>()'" on Clang. Either way the key comes out of stderr with one regular expression, and the demo at the end of this post runs unchanged on all three.

## One trap at a time, and why that is too slow

The obvious algorithm arms one trap per compile. For each probe point, compile each test translation unit with that trap armed, and stop at the first failure. It is trivially correct. It is also `O(probe points × translation units)` full front-end runs of whatever the test suite includes, and a test suite for compile-time code tends to include the expensive things: a reflection-heavy header, googletest, `<string>` and friends.

For the library where I first used this, one compile of the main test file took about thirteen seconds. With 177 probe points and four test files, the job on a CI runner took 36 minutes. My collaborator's reaction was that he would rather not measure consteval coverage at all than wait that long for it, which is a fair position and one I wanted to avoid.

Sharding the probe points across runners helps wall time and does nothing for the bill. The fix is to arm many traps in one compile.

## Arming many traps at once

The reason you can do that is a property of how compilers report errors. A throw aborts only the constant evaluation it happens in. The compiler then carries on with the rest of the translation unit and reports each failing evaluation separately. A `static_assert`, a `constexpr` variable's initializer, a template argument, a `consteval` block: each of those is its own top-level evaluation, and each of them can fail independently in a single `-fsyntax-only` run.

So arm every probe point at once. Each evaluation the test suite performs throws at the first armed trap on its path and reports it. One compile can find dozens of points.

The catch is masking. If two armed traps lie on the same path, only the first reports, because the throw stopped the evaluation before it reached the second. The entry trap of a function masks every trap inside it, in every evaluation that calls the function.

The remedy is to go in rounds. After a compile, disarm every trap it found, and compile again. The evaluations now run past the points that stopped them last time and report the next armed trap on each path. Stop when a round finds nothing new.

It is worth being careful about why this is sound, because "compile with everything armed and read the errors" sounds like it should be full of holes.

**No false positives.** A trap throws only when the evaluator executes it, and the diagnostic names the trap that threw. Every key you read out of stderr was evaluated, no matter what else was armed.

**No permanent false negatives.** Take any probe point the test suite does evaluate. Every armed trap that could mask it is one that runs before it on some path, which means the suite evaluates that one too. So by induction on the path, once its predecessors have been found and disarmed, it reports. The armed set shrinks after every round that finds something, so the process terminates. And when a round finds nothing, no armed trap is on any path the suite takes, which is exactly the statement that the remaining points are uncovered.

**Cascading errors do not matter.** An evaluation that aborts halfway through can leave a class incomplete or a member undeclared, and the compiler then produces a shower of unrelated-looking errors after it. None of those name a trap, so none of them are counted. Any evaluation they suppressed runs in a later round once the trap that caused them is disarmed, by the same argument as above.

**A compile that fails without any trap firing is a bug.** That is the one outcome the algorithm cannot explain, and it means the instrumenter broke the code. Treat it as fatal. It also means you do not need a separate "does the instrumented code still compile" pass: the last round of every run is one.

The rounds are bounded by the length of the longest chain of traps on a single path, not by the number of probe points. On the library I measured, 177 points resolved in 23 rounds.

## Two cheap tricks on top

**Interleave the batches.** Within a round, you can split the armed set into several batches and compile each batch separately, which both uses your cores and reduces masking, since two traps in different batches cannot mask each other. How you split matters. Consecutive probe points in a file are usually on the same path: a function's entry, then its first block, then its return. So stripe them, sending point 1 to batch 1, point 2 to batch 2, and so on, rather than cutting the sorted list into contiguous chunks. On four cores, striping cut the round count from 42 to 23 and the wall time from 155 seconds to 94 compared with contiguous chunks.

**Probe the cheap translation units first.** A probe point is covered as soon as any test file evaluates it. If one test file compiles in two seconds and another in thirteen, run the rounds on the cheap one first, then only arm what it left uncovered when you get to the expensive one. On my measurements the two cheapest test files settled about 60 percent of the points, so the expensive file only ever had to chase the remainder.

With both, the same 177 points that took 36 minutes on the CI runner took three, on a single runner, with results identical to the one-trap-per-compile baseline. Locally, on four cores, it was 94 seconds against 419 seconds for the baseline on 24 cores.

## What it does not do

The probe points are at block and return/throw granularity, not on every line. That is the same granularity a branch-coverage tool reports and is usually what you want, but it is not line coverage.

A branch of `if constexpr` that no instantiation includes reports as unevaluated. That is correct, and it is one of the things you want to find out, but it is a reminder that "covered" here means "some test instantiated and evaluated this".

If the compiler stops after a fixed number of errors, a round can under-report. GCC's default is no limit; if you have `-fmax-errors` in your flags, take it out for the probe compiles. Under-reporting within a round is harmless anyway, since the next round picks up what was missed, but a hard stop before the first evaluation would look like "nothing new" and end the run early. The bug-detection rule catches that case, because such a compile fails with no trap fired.

And the instrumenter is the part you have to write for your own code. Mine is a few hundred lines of Python that tracks strings, comments, brace depth and `consteval` regions, and inserts a trap at every block entry and before every `return` and `throw`. It is a scanner, not a parser, and it works because clang-format keeps the source regular. A cut-down version, enough for the header in the demonstration below, is in the repository. A tool built on libclang would be more general.

## The road not taken

There is a much faster way to get this information, and I want to mention it so you can decide not to use it.

Class template instantiation is memoised per translation unit, and a class template can declare a friend function that a later specialization defines. With that, a trap can record "line 15 was reached" as a permanent fact in the translation unit's state, and a `static_assert` at the end can dump every line that was marked, in a single compile. It works. It is also precisely the "stateful metaprogramming via friend injection" of CWG issue 2118, which the committee has said it wants to make ill-formed and which no compiler owes you. For a tool whose purpose is to make a library's compile-time behaviour trustworthy, building on that felt wrong, and the round-based approach turned out to be fast enough that the question never came back.

## Try it

The repository has two demonstrations. Both need Python 3 and any of GCC 15, GCC 16 or a recent Clang.

The first, `basic_trap_demo`, shows the mechanism with nothing in the way: a small `consteval` name-mangler with hand-placed traps, a test file that deliberately leaves two branches untested, and a 70-line probe script that runs the rounds, one compile each, and prints what the tests missed.

```
$ python3 probe.py mangle.hh mangle_test.cc g++
round 1: 12 armed, 2 hit
round 2: 10 armed, 2 hit
round 3: 8 armed, 1 hit
round 4: 7 armed, 1 hit
round 5: 6 armed, 1 hit
round 6: 5 armed, 1 hit
round 7: 4 armed, 0 hit
  covered   mangle.hh:15  probe::trap<__LINE__>();
  UNCOVERED mangle.hh:18  probe::trap<__LINE__>();
  UNCOVERED mangle.hh:20  probe::trap<__LINE__>(); return out;
  covered   mangle.hh:23  probe::trap<__LINE__>();
  ...
  UNCOVERED mangle.hh:44  probe::trap<__LINE__>();
  UNCOVERED mangle.hh:45  probe::trap<__LINE__>(); throw "division by zero in mangle_ratio";
  ...
8/12 probe points evaluated
```

Read the rounds from the top. Round one finds the two function entries and nothing else, because every other trap sits behind one of them. Round two, with the entries disarmed, gets one step further into each function. Seven rounds later, the zero branch and the division-by-zero throw are the only points left, and the report says so. Add `static_assert(view(mangle_decimal(0)) == "0")` to the test file and run it again.

The second, `advanced_probe_demo`, is the same mangler and the same tests with the tooling the rest of this post describes. Its header has no traps in it. `instrument.py` is the scanner, cut down to 180 lines, and it puts the same twelve traps into a copy of the header in a scratch directory, each on its original line:

```
$ python3 instrument.py mangle.hh | grep -n 'probe::trap'
14:consteval digits mangle_decimal(long long value) { probe::trap<__LINE__>();
16:  if (value == 0) { probe::trap<__LINE__>();
18:    { probe::trap<__LINE__>(); return out; }
20:  if (value < 0) { probe::trap<__LINE__>();
...
```

`probe.py` runs the rounds on that copy. Without `--jobs` it reproduces the seven rounds above from the clean header. With `--jobs 4` it splits each round's armed set into four striped batches and compiles them in parallel:

```
$ python3 probe.py --jobs 4 mangle.hh mangle_test.cc
12 probe points in mangle.hh
mangle_test.cc round 1: 12 armed in 4 batches, 5 hit
mangle_test.cc round 2: 7 armed in 4 batches, 2 hit
mangle_test.cc round 3: 5 armed in 4 batches, 1 hit
mangle_test.cc round 4: 4 armed in 4 batches, 0 hit
  covered   mangle.hh:14  consteval digits mangle_decimal(long long value) {
  UNCOVERED mangle.hh:16  if (value == 0) {
  UNCOVERED mangle.hh:18  return out;
  ...
  UNCOVERED mangle.hh:37  if (denominator == 0) {
  UNCOVERED mangle.hh:38  throw "division by zero in mangle_ratio";
  ...
8/12 probe points evaluated
```

Round one now finds five points, not two. The two function entries are in different batches from the points behind them, so they no longer mask them, and the run settles in four rounds instead of seven. The script also takes several test files and probes them in the order given, arming for each only what the earlier ones left uncovered, which is the cheapest-first trick from above. And `--lcov-output` writes the result as an LCOV trace, one line record per probe point, so it can go through `genhtml` or up to a coverage service alongside the runtime data. The two merge cleanly because they are disjoint: gcov reports nothing for the lines the probe reports on.

*[Code listings: `basic_trap_demo/` and `advanced_probe_demo/` in the repository.]*
