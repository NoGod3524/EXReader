/* SPDX-License-Identifier: MIT */
/* Minimal streaming SHA-256 (FIPS 180-4) for the catalog digest. It is the
   only hashing this package needs; no OpenSSL, CommonCrypto or CNG dependency
   is added for one 32-byte digest. */
#include "internal.h"

#include <string.h>

static const uint32_t rl_sha256_round[64] = {
  0x428a2f98u, 0x71374491u, 0xb5c0fbcfu, 0xe9b5dba5u, 0x3956c25bu, 0x59f111f1u,
  0x923f82a4u, 0xab1c5ed5u, 0xd807aa98u, 0x12835b01u, 0x243185beu, 0x550c7dc3u,
  0x72be5d74u, 0x80deb1feu, 0x9bdc06a7u, 0xc19bf174u, 0xe49b69c1u, 0xefbe4786u,
  0x0fc19dc6u, 0x240ca1ccu, 0x2de92c6fu, 0x4a7484aau, 0x5cb0a9dcu, 0x76f988dau,
  0x983e5152u, 0xa831c66du, 0xb00327c8u, 0xbf597fc7u, 0xc6e00bf3u, 0xd5a79147u,
  0x06ca6351u, 0x14292967u, 0x27b70a85u, 0x2e1b2138u, 0x4d2c6dfcu, 0x53380d13u,
  0x650a7354u, 0x766a0abbu, 0x81c2c92eu, 0x92722c85u, 0xa2bfe8a1u, 0xa81a664bu,
  0xc24b8b70u, 0xc76c51a3u, 0xd192e819u, 0xd6990624u, 0xf40e3585u, 0x106aa070u,
  0x19a4c116u, 0x1e376c08u, 0x2748774cu, 0x34b0bcb5u, 0x391c0cb3u, 0x4ed8aa4au,
  0x5b9cca4fu, 0x682e6ff3u, 0x748f82eeu, 0x78a5636fu, 0x84c87814u, 0x8cc70208u,
  0x90befffau, 0xa4506cebu, 0xbef9a3f7u, 0xc67178f2u
};

static uint32_t rl_rotr(uint32_t value, unsigned bits) {
  return (value >> bits) | (value << (32u - bits));
}

static void rl_sha256_compress(rl_sha256 *hash, const unsigned char block[64]) {
  uint32_t schedule[64];
  uint32_t a, b, c, d, e, f, g, h;
  size_t i;
  for (i = 0; i < 16u; ++i) {
    schedule[i] = ((uint32_t)block[i * 4u] << 24) | ((uint32_t)block[i * 4u + 1u] << 16) |
                  ((uint32_t)block[i * 4u + 2u] << 8) | (uint32_t)block[i * 4u + 3u];
  }
  for (i = 16u; i < 64u; ++i) {
    uint32_t low = rl_rotr(schedule[i - 15u], 7u) ^ rl_rotr(schedule[i - 15u], 18u) ^
                   (schedule[i - 15u] >> 3);
    uint32_t high = rl_rotr(schedule[i - 2u], 17u) ^ rl_rotr(schedule[i - 2u], 19u) ^
                    (schedule[i - 2u] >> 10);
    schedule[i] = schedule[i - 16u] + low + schedule[i - 7u] + high;
  }
  a = hash->state[0];
  b = hash->state[1];
  c = hash->state[2];
  d = hash->state[3];
  e = hash->state[4];
  f = hash->state[5];
  g = hash->state[6];
  h = hash->state[7];
  for (i = 0; i < 64u; ++i) {
    uint32_t mix1 = rl_rotr(e, 6u) ^ rl_rotr(e, 11u) ^ rl_rotr(e, 25u);
    uint32_t choose = (e & f) ^ ((~e) & g);
    uint32_t first = h + mix1 + choose + rl_sha256_round[i] + schedule[i];
    uint32_t mix2 = rl_rotr(a, 2u) ^ rl_rotr(a, 13u) ^ rl_rotr(a, 22u);
    uint32_t majority = (a & b) ^ (a & c) ^ (b & c);
    uint32_t second = mix2 + majority;
    h = g;
    g = f;
    f = e;
    e = d + first;
    d = c;
    c = b;
    b = a;
    a = first + second;
  }
  hash->state[0] += a;
  hash->state[1] += b;
  hash->state[2] += c;
  hash->state[3] += d;
  hash->state[4] += e;
  hash->state[5] += f;
  hash->state[6] += g;
  hash->state[7] += h;
}

void rl_sha256_init(rl_sha256 *hash) {
  hash->state[0] = 0x6a09e667u;
  hash->state[1] = 0xbb67ae85u;
  hash->state[2] = 0x3c6ef372u;
  hash->state[3] = 0xa54ff53au;
  hash->state[4] = 0x510e527fu;
  hash->state[5] = 0x9b05688cu;
  hash->state[6] = 0x1f83d9abu;
  hash->state[7] = 0x5be0cd19u;
  hash->bits = 0u;
  hash->used = 0u;
  memset(hash->block, 0, sizeof(hash->block));
}

void rl_sha256_update(rl_sha256 *hash, const void *data, size_t length) {
  const unsigned char *bytes = (const unsigned char *)data;
  hash->bits += (uint64_t)length * 8u;
  while (length > 0u) {
    size_t room = sizeof(hash->block) - hash->used;
    size_t take = length < room ? length : room;
    memcpy(hash->block + hash->used, bytes, take);
    hash->used += take;
    bytes += take;
    length -= take;
    if (hash->used == sizeof(hash->block)) {
      rl_sha256_compress(hash, hash->block);
      hash->used = 0u;
    }
  }
}

void rl_sha256_update_string(rl_sha256 *hash, const char *text) {
  rl_sha256_update(hash, text, strlen(text));
}

void rl_sha256_final(rl_sha256 *hash, unsigned char out[32]) {
  uint64_t bits = hash->bits;
  unsigned char marker = 0x80u;
  unsigned char zero = 0x00u;
  unsigned char high;
  size_t i;
  rl_sha256_update(hash, &marker, 1u);
  while (hash->used != 56u) {
    rl_sha256_update(hash, &zero, 1u);
  }
  for (i = 0u; i < 8u; ++i) {
    high = (unsigned char)((bits >> (56u - 8u * i)) & 0xffu);
    rl_sha256_update(hash, &high, 1u);
  }
  for (i = 0u; i < 8u; ++i) {
    out[i * 4u] = (unsigned char)(hash->state[i] >> 24);
    out[i * 4u + 1u] = (unsigned char)(hash->state[i] >> 16);
    out[i * 4u + 2u] = (unsigned char)(hash->state[i] >> 8);
    out[i * 4u + 3u] = (unsigned char)hash->state[i];
  }
}
