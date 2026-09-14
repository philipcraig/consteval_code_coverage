#!/bin/sh
# Check that the instrumented demo compiles with no trap armed, then probe
# which probe points the test suite evaluates. Set CXX to choose a compiler.
set -eu
cd "$(dirname "$0")/demo"
CXX="${CXX:-g++}"

echo "unarmed compile with $CXX"
"$CXX" -std=c++23 -fsyntax-only -include unarmed.h mangle_test.cc

echo "probing"
python3 probe.py mangle.hh mangle_test.cc "$CXX"
