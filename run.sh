#!/bin/sh
# Run both demos. Set CXX to choose a compiler.
#
# basic_trap_demo: a header with traps placed by hand, and a prober that arms
# the untested traps and runs one compile per round until nothing new fires.
# advanced_probe_demo: the same header with no traps in it; an instrumenter
# inserts them into a copy, and the prober splits each round into
# interleaved batches compiled in parallel.
set -eu
cd "$(dirname "$0")"
CXX="${CXX:-g++}"

echo "== basic_trap_demo: unarmed compile with $CXX"
(cd basic_trap_demo && "$CXX" -std=c++23 -fsyntax-only -include unarmed.h mangle_test.cc)
echo "== basic_trap_demo: one compile per round"
(cd basic_trap_demo && python3 probe.py mangle.hh mangle_test.cc "$CXX")

echo "== advanced_probe_demo: what instrument.py inserts into mangle.hh"
(cd advanced_probe_demo && python3 instrument.py mangle.hh | grep -n 'probe::trap')
echo "== advanced_probe_demo: one compile per round"
(cd advanced_probe_demo && python3 probe.py --compiler "$CXX" mangle.hh mangle_test.cc)
echo "== advanced_probe_demo: four interleaved batches per round"
(cd advanced_probe_demo && python3 probe.py --compiler "$CXX" --jobs 4 mangle.hh mangle_test.cc)
