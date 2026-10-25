# SPDX-License-Identifier: MIT
# S11 independent consumer: installed packages only, no build-tree include dirs.
cmake_minimum_required(VERSION 3.24)
project(reader_final_s11_consumer LANGUAGES C)
if(MSVC)
  add_compile_options(/utf-8)
endif()
find_package(EXReader 3.41.0 EXACT CONFIG REQUIRED COMPONENTS library)
find_package(EXReaderSideload CONFIG REQUIRED)
find_package(EXReaderBatchImport CONFIG REQUIRED)
find_package(EXReaderCloudImport CONFIG REQUIRED)
find_package(EXReaderLocalDownloads CONFIG REQUIRED)
find_package(EXReaderProductCatalog CONFIG REQUIRED)
add_executable(s11-probe s11_probe.c)
target_link_libraries(s11-probe PRIVATE
  EXReaderSideload::exr_sideload
  EXReaderBatchImport::reader_batch_import
  EXReaderCloudImport::reader_cloud_import
  EXReaderLocalDownloads::reader_local_downloads
  EXReaderProductCatalog::reader_catalog)
set_target_properties(s11-probe PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON)
