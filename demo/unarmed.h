// The trap header with nothing armed: every trap is an empty function.
// probe.py generates the armed variants; this one is for ordinary builds
// of the instrumented header.
namespace probe {
template <long Line> struct trap_hit {};
template <long Line> constexpr bool armed = false;
template <long Line> constexpr void trap() {
  if consteval {
    if constexpr (armed<Line>) throw trap_hit<Line>{};
  }
}
}  // namespace probe
