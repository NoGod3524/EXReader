# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(DFinalCModels LANGUAGES C CXX)
find_package(Python3 REQUIRED COMPONENTS Interpreter)
find_package(EXReaderProductCatalog 0.1.0 EXACT CONFIG REQUIRED)
# Reuse the installed consumer of the exact raw3 APIs called by HostWave3.swift.
add_subdirectory(../reader_next_c06/consumer consumer)
enable_testing()
add_test(NAME dfinal-c-annotation-exchange-model
  COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/check_exchange.py"
    --probe $<TARGET_FILE:c06-probe> --output "${CMAKE_CURRENT_BINARY_DIR}/results")
set_tests_properties(dfinal-c-annotation-exchange-model PROPERTIES TIMEOUT 300)
add_test(NAME dfinal-c-installed-sdk-version-guard
  COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/check_version_guard.py"
    --prefixes "${CMAKE_PREFIX_PATH}")
add_executable(dfinal-c-catalog-upgrade catalog_upgrade.c)
target_link_libraries(dfinal-c-catalog-upgrade PRIVATE EXReaderProductCatalog::reader_catalog)
if(MSVC)
  set_property(TARGET dfinal-c-catalog-upgrade PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
endif()
add_test(NAME dfinal-c-product-catalog-upgrade
  COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/check_catalog_upgrade.py"
    --probe $<TARGET_FILE:dfinal-c-catalog-upgrade> --output "${CMAKE_CURRENT_BINARY_DIR}/results")
set_tests_properties(dfinal-c-product-catalog-upgrade PROPERTIES TIMEOUT 60)
