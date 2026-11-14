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
