// The test suite: every call here is a separate top-level constant
// evaluation. Zero and the division-by-zero throw are never exercised.
#include "mangle.hh"

#include <string_view>

consteval std::string_view view(const digits& d) {
  return {d.text.data(), d.size};
}

static_assert(view(mangle_decimal(42)) == "42");
static_assert(view(mangle_decimal(-7)) == "n7");
static_assert(view(mangle_ratio(3, 10)) == "3/10");

template <long long N>
struct tagged {
  static constexpr digits name = mangle_decimal(N);
};

static_assert(view(tagged<1234>::name) == "1234");
static_assert(view(tagged<-1>::name) == "n1");

int main() {}
