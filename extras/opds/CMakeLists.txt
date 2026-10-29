cmake_minimum_required(VERSION 3.24)
# Stand-alone OPDS client. Not part of the default SDK build: configure this directory on its own.
#   cmake -S extras/opds -B build/opds [-DEXR_SDK=<installed SDK prefix>]
# Without EXR_SDK only the network-free client library is built; with it the SDK glue,
# the consumer example and the acceptance driver are built against the installed SDK.
project(EXReaderOPDS VERSION 0.2.0 LANGUAGES C)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

option(EXREADER_OPDS_HASH_ONLY "Build only the independent installed streaming hash owner" OFF)
if(EXREADER_OPDS_HASH_ONLY)
  include(CMakePackageConfigHelpers)
  add_library(opds_sha256_stream STATIC src/opds_sha256_stream.c)
  target_include_directories(opds_sha256_stream PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include/exreader-opds-hash> PRIVATE src)
  if(MSVC)
    target_compile_options(opds_sha256_stream PRIVATE /W4 /WX)
  else()
    target_compile_options(opds_sha256_stream PRIVATE -Wall -Wextra -Werror)
  endif()
  install(TARGETS opds_sha256_stream EXPORT EXReaderOPDSHashTargets ARCHIVE DESTINATION lib)
  install(FILES include/opds_sha256_stream.h DESTINATION include/exreader-opds-hash)
  install(EXPORT EXReaderOPDSHashTargets NAMESPACE EXReaderOPDSHash::
    DESTINATION lib/cmake/EXReaderOPDSHash)
  configure_package_config_file(EXReaderOPDSHashConfig.cmake.in
    "${CMAKE_CURRENT_BINARY_DIR}/EXReaderOPDSHashConfig.cmake"
    INSTALL_DESTINATION lib/cmake/EXReaderOPDSHash)
  write_basic_package_version_file("${CMAKE_CURRENT_BINARY_DIR}/EXReaderOPDSHashConfigVersion.cmake"
    VERSION 0.1.0 COMPATIBILITY ExactVersion)
  install(FILES "${CMAKE_CURRENT_BINARY_DIR}/EXReaderOPDSHashConfig.cmake"
    "${CMAKE_CURRENT_BINARY_DIR}/EXReaderOPDSHashConfigVersion.cmake"
    DESTINATION lib/cmake/EXReaderOPDSHash)
  return()
endif()

add_library(opds STATIC src/opds_core.c src/opds_xml.c src/opds_feed.c src/opds_net.c src/opds_fs.c src/opds_client.c)
target_include_directories(opds PUBLIC include PRIVATE src)
if(WIN32)
  target_link_libraries(opds PUBLIC ws2_32)
endif()
if(NOT MSVC)
  target_compile_options(opds PRIVATE -Wall -Wextra -Wno-unused-parameter)
endif()

enable_testing()
add_executable(opds-facet-test ../../tests/opds/facet_test.c)
target_link_libraries(opds-facet-test PRIVATE opds)
add_test(NAME opds-facets COMMAND opds-facet-test "${CMAKE_BINARY_DIR}/facet-result.json")

if(EXR_SDK)
  list(PREPEND CMAKE_PREFIX_PATH "${EXR_SDK}")
  find_package(EXReader CONFIG REQUIRED COMPONENTS core)
  add_library(opds_sdk STATIC sdk/opds_sdk.c)
  target_include_directories(opds_sdk PUBLIC sdk)
  target_link_libraries(opds_sdk PUBLIC opds EXReader::exr_core)
  add_executable(opds-consume examples/opds_consume.c)
  target_link_libraries(opds-consume PRIVATE opds_sdk)
  add_executable(opds-test ${CMAKE_CURRENT_SOURCE_DIR}/../../tests/opds/opds_test.c)
  target_link_libraries(opds-test PRIVATE opds_sdk)
  add_executable(opds-publish-fault-test ../../tests/opds/publish_fault_test.c)
  target_include_directories(opds-publish-fault-test PRIVATE include src)
  if(WIN32)
    target_link_libraries(opds-publish-fault-test PRIVATE shell32)
  endif()
endif()
