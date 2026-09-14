// A small consteval library: encode an integer as a decimal digit string,
// the way an ABI name-mangler would. This copy is instrumented: each
// `probe::trap<__LINE__>()` marks a block entry or a return/throw.
#pragma once
#include <array>
#include <cstddef>

struct digits {
  std::array<char, 24> text{};
  std::size_t size = 0;
  constexpr void push(char c) { text[size++] = c; }
};

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
  std::array<char, 20> reversed{};
  std::size_t count = 0;
  while (value > 0) {
    probe::trap<__LINE__>();
    reversed[count++] = static_cast<char>('0' + value % 10);
    value /= 10;
  }
  while (count > 0) {
    probe::trap<__LINE__>();
    out.push(reversed[--count]);
  }
  probe::trap<__LINE__>(); return out;
}

consteval digits mangle_ratio(long long numerator, long long denominator) {
  probe::trap<__LINE__>();
  if (denominator == 0) {
    probe::trap<__LINE__>();
    probe::trap<__LINE__>(); throw "division by zero in mangle_ratio";
  }
  digits out = mangle_decimal(numerator);
  out.push('/');
  digits den = mangle_decimal(denominator);
  for (std::size_t i = 0; i < den.size; ++i) {
    probe::trap<__LINE__>();
    out.push(den.text[i]);
  }
  probe::trap<__LINE__>(); return out;
}
