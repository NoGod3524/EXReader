# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(DFinalCModels LANGUAGES C CXX)
find_package(Python3 REQUIRED COMPONENTS Interpreter)
# Reuse the installed consumer of the exact raw3 APIs called by HostWave3.swift.
add_subdirectory(../reader_next_c06/consumer consumer)
enable_testing()
add_test(NAME dfinal-c-annotation-exchange-model
  COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/check_exchange.py"
    --probe $<TARGET_FILE:c06-probe> --output "${CMAKE_CURRENT_BINARY_DIR}/results")
set_tests_properties(dfinal-c-annotation-exchange-model PROPERTIES TIMEOUT 300)
add_test(NAME dfinal-c-android-abi-inspection
  COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/check_android_abi.py")
add_test(NAME dfinal-c-installed-sdk-version-guard
  COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/check_version_guard.py"
    --prefixes "${CMAKE_PREFIX_PATH}")
find_package(EXReaderProductCatalog CONFIG REQUIRED)
add_executable(dfinal-c-catalog-upgrade check_catalog_upgrade.c)
target_compile_features(dfinal-c-catalog-upgrade PRIVATE c_std_11)
if(MSVC)
  set_property(TARGET dfinal-c-catalog-upgrade PROPERTY MSVC_RUNTIME_LIBRARY
    "MultiThreaded$<$<CONFIG:Debug>:Debug>")
endif()
target_link_libraries(dfinal-c-catalog-upgrade PRIVATE
  EXReaderProductCatalog::reader_catalog EXReaderProductCatalog::reader_catalog_sqlite)
add_test(NAME dfinal-c-product-catalog-upgrade
  COMMAND dfinal-c-catalog-upgrade
    "${CMAKE_CURRENT_SOURCE_DIR}/../../apps/reader/store/001_catalog.sql"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../apps/reader/store/002_originals.sql"
    "${CMAKE_CURRENT_BINARY_DIR}")
