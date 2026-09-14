// A small consteval library: encode an integer as a decimal digit string,
// the way an ABI name-mangler would. This is the code under test, with no
// traps in it; instrument.py inserts them into a copy.
#pragma once
#include <array>
#include <cstddef>

struct digits {
  std::array<char, 24> text{};
  std::size_t size = 0;
  constexpr void push(char c) { text[size++] = c; }
};

consteval digits mangle_decimal(long long value) {
  digits out;
  if (value == 0) {
    out.push('0');
    return out;
  }
  if (value < 0) {
    out.push('n');
    value = -value;
  }
  std::array<char, 20> reversed{};
  std::size_t count = 0;
  while (value > 0) {
    reversed[count++] = static_cast<char>('0' + value % 10);
    value /= 10;
  }
  while (count > 0) {
    out.push(reversed[--count]);
  }
  return out;
}

consteval digits mangle_ratio(long long numerator, long long denominator) {
  if (denominator == 0) {
    throw "division by zero in mangle_ratio";
  }
  digits out = mangle_decimal(numerator);
  out.push('/');
  digits den = mangle_decimal(denominator);
  for (std::size_t i = 0; i < den.size; ++i) {
    out.push(den.text[i]);
  }
  return out;
}
