# SPDX-License-Identifier: MIT
# Builds the unchanged cloud_probe.c against the installed SDK without the original consumer's
# `EXReader 3.40.0 EXACT` pin (the fixed start installs SDK 3.41.0; see docs/reader-final-c03).
cmake_minimum_required(VERSION 3.24)
project(reader_final_c03_probe LANGUAGES C CXX)
set(CMAKE_C_STANDARD 11)
find_package(EXReader CONFIG REQUIRED COMPONENTS library)
find_package(EXReaderSideload CONFIG REQUIRED)
find_package(EXReaderWebDAV CONFIG REQUIRED)
find_package(EXReaderCloudImport 0.1.0 EXACT CONFIG REQUIRED)
add_executable(cloud-probe ${CMAKE_CURRENT_SOURCE_DIR}/../../reader_webdav_import/consumer/cloud_probe.c)
target_link_libraries(cloud-probe PRIVATE EXReaderCloudImport::reader_cloud_import)
