# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.21)
project(ledger_credential_identity_probe C)
find_package(EXReaderCredentials CONFIG REQUIRED)
add_executable(credential-identity-probe credential_identity_probe.c)
target_link_libraries(credential-identity-probe PRIVATE EXReaderCredentials::exr_credentials advapi32 secur32 userenv ole32)
