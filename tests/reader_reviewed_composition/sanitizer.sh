#!/usr/bin/env bash
# Supplemental original J13 ASan/UBSan contract; execution only in Actions.
set -euo pipefail
test "${GITHUB_ACTIONS:-}" = true
out="$PWD/build/composition/original/sanitizer"
build="$PWD/build/reviewed-asan"
mkdir -p "$out" "$build/store"
flags='-fsanitize=address,undefined -fno-omit-frame-pointer -g'
cmake -S apps/reader/account-profiles -B "$build/package" -G Ninja -DCMAKE_BUILD_TYPE=Debug -DCMAKE_C_FLAGS="$flags" -DCMAKE_INSTALL_PREFIX="$build/prefix" 2>&1 | tee "$out/configure.log"
cmake --build "$build/package" --parallel 4 2>&1 | tee "$out/build.log"
cmake --install "$build/package" 2>&1 | tee "$out/install.log"
cmake -S tests/reader_account_profiles/consumer -B "$build/consumer" -G Ninja -DCMAKE_BUILD_TYPE=Debug -DEXR_ACCOUNT_PROFILES_SESSION=OFF -DCMAKE_PREFIX_PATH="$build/prefix" -DCMAKE_C_FLAGS="$flags" -DCMAKE_CXX_FLAGS="$flags" -DCMAKE_EXE_LINKER_FLAGS='-fsanitize=address,undefined' -DEXR_ACCOUNT_PROFILES_SOURCE="$PWD/apps/reader/account-profiles/src" -DEXR_ACCOUNT_PROFILES_INCLUDE="$PWD/apps/reader/account-profiles/include" 2>&1 | tee "$out/consumer-configure.log"
cmake --build "$build/consumer" --parallel 4 2>&1 | tee "$out/consumer-build.log"
export ASAN_OPTIONS='detect_leaks=1:halt_on_error=1:detect_stack_use_after_return=1'
export UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1'
S="$build/store";P="$build/consumer/profiles-probe";W="$build/consumer/profiles-worker"
"$P" info | tee "$out/info.log"
"$P" add "$S" a1000000-0000-4000-8000-000000000001 b1000000-0000-4000-8000-000000000001 https://asan.example/reader/ 阅读器 | tee "$out/add.log"
"$P" load "$S" | tee "$out/load.log"
"$P" activation "$S" a1000000-0000-4000-8000-000000000001 | tee "$out/activation.log"
"$P" verify-tampered "$S" a1000000-0000-4000-8000-000000000001 | tee "$out/verify.log"
"$P" verify-nonterminated | tee "$out/nonterminated-plan.log"
"$W" add "$S" a1000000-0000-4000-8000-000000000002 b1000000-0000-4000-8000-000000000002 https://asan.example/reader/ two --cancel-before-rename | tee "$out/cancel.log"
"$P" add-gen "$S" a1000000-0000-4000-8000-000000000003 b1000000-0000-4000-8000-000000000003 https://asan.example/reader/ three 0 | tee "$out/conflict.log"
cp "$P" "$out/profiles-probe-asan"
cp "$W" "$out/profiles-worker-asan"
printf 'failures=0\n' > "$out/sanitizer.txt"
