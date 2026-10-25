/* Exercise the actual C trap wrapper with a deliberately hostile mock module.
 * This test never substitutes its module for a real compiler qualification. */
#include "NativeCompilerAPI.h"
#include "native-checkpoint.h"
#include "rustc.h"
#include <assert.h>
#include <pthread.h>
#include <stdio.h>
#include <string.h>

static int mode, polls, returned_from_nested_trap;
static CrabrixNativeCompiler* current;

void wasm2c_crabrix__rustc_instantiate(w2c_crabrix__rustc* m,
    struct w2c_crabrix__proc__macro__v1* p, struct w2c_wasi__snapshot__preview1* w) {
  m->w2c_crabrix__proc__macro__v1_instance = p;
  m->w2c_wasi__snapshot__preview1_instance = w;
  wasm_rt_allocate_memory(&m->w2c_memory, 1, 65536, false, 65536);
}
void wasm2c_crabrix__rustc_free(w2c_crabrix__rustc* m) { wasm_rt_free_memory(&m->w2c_memory); }
u32 w2c_crabrix__rustc_0x5F_crabrix_pm_alloc(w2c_crabrix__rustc* m, u32 n) { return 64; }
void w2c_crabrix__rustc_0x5F_crabrix_pm_free(w2c_crabrix__rustc* m, u32 p, u32 n) {}
u64 w2c_crabrix__rustc_0x5F_crabrix_pm_dispatch(w2c_crabrix__rustc* m, u32 p, u32 n) {
  wasm_rt_trap(WASM_RT_TRAP_OOB);
}
void w2c_crabrix__rustc_0x5Fstart(w2c_crabrix__rustc* m) {
  if (mode == 1 || mode == 2) for (;;) crabrix_native_checkpoint();
  if (mode == 3) wasm_rt_trap(WASM_RT_TRAP_OOB);
  if (mode == 4) w2c_crabrix__proc__macro__v1_exchange(m->w2c_crabrix__proc__macro__v1_instance, 0, 0, 0, 0, 0, 0);
  if (mode == 5) {
    crabrix_native_active_budget->stack_low = (uintptr_t)__builtin_frame_address(0);
    crabrix_native_checkpoint();
  }
  if (mode == 6) {
    assert(m->w2c_memory.max_pages == 32768);
    assert(wasm_rt_grow_memory(&m->w2c_memory, 32768) == UINT64_MAX);
  }
}
static int32_t host(void* context, const char* module, const char* name,
                    const uint64_t* args, uint32_t count, uint64_t* result) {
  uint64_t nested = 0;
  assert(crabrix_native_compiler_export(current, 3, 0, 0, &nested) != 0);
  returned_from_nested_trap = 1;
  *result = 0;
  return 0;
}
static int32_t poll_host(void* context) { return mode == 2 && ++polls >= 3; }
static void* tests(void* context) {
  assert(crabrix_native_compiler_memory(NULL) == NULL);
  assert(crabrix_native_compiler_export(NULL, 1, 0, 0, NULL) == -2);
  for (int i = 0; i < 7; ++i) {
    mode = i; polls = 0;
    current = crabrix_native_compiler_create(NULL, host, poll_host);
    assert(current);
    int trap = crabrix_native_compiler_run(current, mode == 1 ? 100 : 1000000);
    if (mode == 1 || mode == 2 || mode == 3 || mode == 5) assert(trap != 0);
    else assert(trap == 0);
    if (mode == 1) assert(crabrix_native_compiler_remaining_work(current) == 0);
    if (mode == 2) assert(polls == 3);
    if (mode == 4) assert(returned_from_nested_trap);
    assert(crabrix_native_compiler_run(current, 100) == -2);
    crabrix_native_compiler_free(current);
  }
  puts("Native guards: budget, cancellation, OOB, nested C traps, stack margin, 2 GiB limit and repeated teardown passed");
  return NULL;
}
int main(void) {
  pthread_attr_t attributes;
  pthread_attr_init(&attributes);
  pthread_attr_setstacksize(&attributes, 32 * 1024 * 1024);
  pthread_t thread;
  assert(pthread_create(&thread, &attributes, tests, NULL) == 0);
  pthread_join(thread, NULL);
  pthread_attr_destroy(&attributes);
}
