//===-- atomic.c - Implement support functions for atomic operations.------===//
//
// Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//
// Query-only subset of LLVM compiler-rt 19.1.7 atomic.c.
// https://github.com/llvm/llvm-project/blob/llvmorg-19.1.7/compiler-rt/lib/builtins/atomic.c
// Original atomic.c SHA256: 9fcf5fc6f0cb1da23f004fa9bc3af1cfcb5589f0c8d20e7b6de863591b60eb98

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#pragma redefine_extname __atomic_is_lock_free_c __atomic_is_lock_free

/// Macros for determining whether a size is lock free.
#define ATOMIC_ALWAYS_LOCK_FREE_OR_ALIGNED_LOCK_FREE(size, p)                  \
  (__atomic_always_lock_free(size, p) ||                                       \
   (__atomic_always_lock_free(size, 0) && ((uintptr_t)p % size) == 0))
#define IS_LOCK_FREE_1(p) ATOMIC_ALWAYS_LOCK_FREE_OR_ALIGNED_LOCK_FREE(1, p)
#define IS_LOCK_FREE_2(p) ATOMIC_ALWAYS_LOCK_FREE_OR_ALIGNED_LOCK_FREE(2, p)
#define IS_LOCK_FREE_4(p) ATOMIC_ALWAYS_LOCK_FREE_OR_ALIGNED_LOCK_FREE(4, p)
#define IS_LOCK_FREE_8(p) ATOMIC_ALWAYS_LOCK_FREE_OR_ALIGNED_LOCK_FREE(8, p)
#define IS_LOCK_FREE_16(p) ATOMIC_ALWAYS_LOCK_FREE_OR_ALIGNED_LOCK_FREE(16, p)

/// Whether atomic operations for the given size (and alignment) are lock-free.
bool __atomic_is_lock_free_c(size_t size, void *ptr) {
  switch (size) {
#define CASE(n) case n: return ATOMIC_ALWAYS_LOCK_FREE_OR_ALIGNED_LOCK_FREE(n, ptr)
    CASE(1);
    CASE(2);
    CASE(4);
    CASE(8);
#ifdef __SIZEOF_INT128__
    CASE(16);
#endif
#undef CASE
  default:
    break;
  }
  return false;
}

