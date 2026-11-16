# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.21)
project(ledger_public_tls_probe C CXX)
find_package(EXReaderWebDAV 0.2.0 EXACT CONFIG REQUIRED)
add_executable(public-tls-probe public_tls_probe.c)
target_link_libraries(public-tls-probe PRIVATE EXReaderWebDAV::exr_webdav)
if(WIN32)
  target_link_libraries(public-tls-probe PRIVATE winhttp xmllite)
endif()
