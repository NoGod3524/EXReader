cmake_minimum_required(VERSION 3.24)
# Stand-alone OPDS client. Not part of the default SDK build: configure this directory on its own.
#   cmake -S extras/opds -B build/opds [-DEXR_SDK=<installed SDK prefix>]
# Without EXR_SDK only the network-free client library is built; with it the SDK glue,
# the consumer example and the acceptance driver are built against the installed SDK.
project(EXReaderOPDS VERSION 0.1.0 LANGUAGES C)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

add_library(opds STATIC src/opds_core.c src/opds_xml.c src/opds_feed.c src/opds_net.c src/opds_fs.c src/opds_client.c)
target_include_directories(opds PUBLIC include PRIVATE src)
if(WIN32)
  target_link_libraries(opds PUBLIC ws2_32)
endif()
if(NOT MSVC)
  target_compile_options(opds PRIVATE -Wall -Wextra -Wno-unused-parameter)
endif()

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
endif()
