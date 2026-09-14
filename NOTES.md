# Author notes for the consteval coverage post

## Files

- `post.md`: the article, about 2,450 words, first person. Its last section
  points at the listings in `demo/`; paste them as code blocks there, or
  link this repository.
- `basic_trap_demo/` and `advanced_probe_demo/`: the two runnable examples
  the last section shows; `run.sh` at the root runs both.
- To render the post for pasting into an editor:
  `uv run --no-project --with markdown python -c "import markdown,sys;
  print(markdown.markdown(sys.stdin.read(), extensions=['fenced_code']))"
  < post.md > post.html`. Pasting rendered HTML keeps headings and code
  blocks; pasting raw Markdown does not.

## Verified before publishing

- The demo output in the post is real: GCC 15.2 (stock Ubuntu), GCC 17
  trunk (20260816) and a clang-p2996 build all give 8/12 in 7 rounds with
  the same four uncovered points. The advanced demo gives the same 7 rounds
  serially and 4 rounds with `--jobs 4` on GCC 15.2, GCC 16 trunk
  (20260322) and clang-p2996 (2026-09-14).
- On GCC 15 and Clang the throw is "not a constant expression" rather than
  an uncaught exception; the script reads the trap key from the note chain
  in that case. Constexpr exceptions (P3068) are GCC 16+.
- `-std=c++23` is enough for the demo (`if consteval`). C++20 would need
  `std::is_constant_evaluated()` instead.

## Numbers quoted in the post (all measured 2026-09-13)

| Claim | Source |
|---|---|
| one compile of the main test file ~13 s | local unarmed -fsyntax-only, 13.0 s |
| 177 probe points, 4 test files, 36 min on CI | unsharded CI probe step 36.3 min |
| 3 min on one runner after the change | CI probe step 3 min 3 s |
| 94 s on 4 cores vs 419 s baseline on 24 cores | local runs |
| striping: 42 → 23 rounds, 155 s → 94 s | local 4-core runs |
| two cheapest test files settle ~60 % of points | 107/177 |
| 177 points in 23 rounds | 4-core run |


## Publishing ideas / open items

- Credit: the batched-round idea and the template-argument trick came from
  a collaborator's prototype. Name Jonathan Coe if he is happy with that;
  the post currently says "my collaborator" once and otherwise "I".
- Title alternatives: "Coverage for code that never runs"; "Measuring
  consteval coverage by making the build fail"; "One bit per evaluation".
- Suggested subtitle: "Runtime coverage tools cannot see consteval code.
  The compiler's own error reporting can stand in for them."
- Pull quote candidate: "There is exactly one thing a constant evaluation
  can do that the outside world notices: it can fail."
- Tags: C++, C++26, reflection, testing, coverage, consteval.
- The "road not taken" section names CWG 2118 by number; link
  https://cplusplus.github.io/CWG/issues/2118.html.
