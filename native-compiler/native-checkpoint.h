#ifndef CRABRIX_NATIVE_CHECKPOINT_H
#define CRABRIX_NATIVE_CHECKPOINT_H
#include "NativeCompilerAPI.h"
#include "wasm-rt.h"
#include <stddef.h>
typedef struct {
  uint64_t remaining;
  uint32_t ticks;
  uintptr_t stack_low;
  void* context;
  CrabrixNativePoll poll;
} CrabrixNativeBudget;
// The guarded entry lock permits exactly one native compiler at a time.
extern CrabrixNativeBudget* crabrix_native_active_budget;
static inline void crabrix_native_checkpoint(void) {
  CrabrixNativeBudget* budget = crabrix_native_active_budget;
  if (!budget || budget->remaining == 0) wasm_rt_trap(WASM_RT_TRAP_EXHAUSTION);
  --budget->remaining;
  // Clang also rejects single native frames above 128 KiB. This margin lets
  // the next prologue reject recursion before reaching the thread guard page.
  if ((uintptr_t)__builtin_frame_address(0) < budget->stack_low + 512 * 1024)
    wasm_rt_trap(WASM_RT_TRAP_EXHAUSTION);
  if ((++budget->ticks & 127) == 0 && budget->poll && budget->poll(budget->context))
    wasm_rt_trap(WASM_RT_TRAP_UNREACHABLE);
}
#endif
