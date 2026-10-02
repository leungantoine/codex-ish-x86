// Exercise the actual 32-bit atomic ABI and linked OpenSSL, including alignment.
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <pthread.h>
#include <openssl/crypto.h>
#include <openssl/evp.h>
extern bool runtime_query(size_t, void *) __asm__("__atomic_is_lock_free");
extern int CRYPTO_atomic_add64(uint64_t *, uint64_t, uint64_t *, CRYPTO_RWLOCK *);
static uint64_t builtin_count __attribute__((aligned(8)));
static uint64_t openssl_count __attribute__((aligned(8)));
static unsigned char fallback_storage[16] __attribute__((aligned(8)));
static CRYPTO_RWLOCK *crypto_lock;
static const unsigned char expected[32] = {
    0xf0, 0x6b, 0xcf, 0x93, 0x48, 0x2e, 0x5b, 0x21, 0x12, 0x73, 0xdb, 0x68, 0xa9, 0xe2, 0x2a, 0x54, 0x27, 0xbe, 0xa7, 0x54, 0x58, 0xe0, 0x66, 0x92, 0x6f, 0x4e, 0x75, 0xc3, 0x11, 0x08, 0x21, 0x92
};
static void *worker(void *unused) {
    (void)unused;
    for (unsigned n = 0; n < 1000; n++) {
        uint64_t result;
        __atomic_fetch_add(&builtin_count, 1, __ATOMIC_SEQ_CST);
        assert(CRYPTO_atomic_add64(&openssl_count, 1, &result, crypto_lock));
        // This address is naturally aligned for i386 uint64_t, but not 8-aligned.
        // LLVM's query must select OpenSSL's existing lock-protected fallback.
        assert(CRYPTO_atomic_add64((uint64_t *)(fallback_storage + 4), 1, &result, crypto_lock));
        if (n < 50) {
            unsigned char digest[32]; unsigned length;
            assert(EVP_Digest("ish-atomic-test", 15, digest, &length, EVP_sha256(), NULL));
            assert(length == sizeof(expected) && !memcmp(digest, expected, sizeof(expected)));
        }
    }
    return NULL;
}
int main(void) {
    assert(sizeof(void *) == 4);
    bool (*volatile query)(size_t, void *) = runtime_query;
    assert(query(1, fallback_storage));
    assert(query(2, fallback_storage));
    assert(query(4, fallback_storage));
    assert(query(8, &builtin_count));
    assert(!query(3, fallback_storage));
    assert(!query(16, fallback_storage));
    assert(!query(2, fallback_storage + 1));
    assert(!query(4, fallback_storage + 1));
    assert(!query(8, fallback_storage + 4));
    assert(OPENSSL_init_crypto(0, NULL));
    crypto_lock = CRYPTO_THREAD_lock_new(); assert(crypto_lock);
    pthread_t workers[4];
    for (unsigned n=0;n<4;n++) assert(!pthread_create(&workers[n], NULL, worker, NULL));
    for (unsigned n=0;n<4;n++) assert(!pthread_join(workers[n], NULL));
    uint64_t fallback_count; memcpy(&fallback_count, fallback_storage + 4, sizeof(fallback_count));
    assert(builtin_count == 4000 && openssl_count == 4000 && fallback_count == 4000);
    CRYPTO_THREAD_lock_free(crypto_lock);
    printf("PASS: LLVM atomic query alignment, 64-bit concurrent updates, OpenSSL atomic/locked updates and SHA256; %s\n", OpenSSL_version(OPENSSL_VERSION));
    return 0;
}
