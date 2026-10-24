cmake_minimum_required(VERSION 3.22.1)
project(exreader_host C CXX)
option(EXR_HOST_SYNC "Install the optional native account/sync host integration" OFF)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

if(NOT EXR_SDK)
  message(FATAL_ERROR "EXR_SDK must point at an installed EXReader SDK")
endif()

# The Android toolchain otherwise restricts package lookup to the NDK sysroot.
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE BOTH)
list(APPEND CMAKE_PREFIX_PATH "${EXR_SDK}")
set(EXReader_DIR "${EXR_SDK}/lib/cmake/EXReader" CACHE PATH "Installed EXReader package" FORCE)
find_package(EXReader 3.40.0 EXACT CONFIG REQUIRED)

add_library(exreader_host SHARED exreader_host_jni.c)
target_link_libraries(exreader_host PRIVATE EXReader::exreader)
target_compile_options(exreader_host PRIVATE -Wall -Wextra)
target_link_options(exreader_host PRIVATE -Wl,-z,max-page-size=16384)

# Installed product modules use their own SQLite provider; the frozen SDK stays
# in the original host library. Hide archive symbols against Android interpose.
if(NOT EXR_PRODUCT)
  message(FATAL_ERROR "EXR_PRODUCT must point at installed native product packages")
endif()
list(APPEND CMAKE_PREFIX_PATH "${EXR_PRODUCT}")
find_package(EXReaderCommands 0.1.0 EXACT CONFIG REQUIRED)
add_library(exreader_product SHARED catalog_jni.cpp)
target_compile_features(exreader_product PRIVATE cxx_std_17)
target_link_libraries(exreader_product PRIVATE EXReaderCommands::reader_commands
  EXReaderProductCatalog::reader_catalog EXReaderProductCatalog::reader_catalog_sqlite dl)
target_compile_options(exreader_product PRIVATE -Wall -Wextra -fvisibility=hidden)
target_link_options(exreader_product PRIVATE -Wl,-z,max-page-size=16384 -Wl,--exclude-libs,ALL
  -Wl,-Bsymbolic -Wl,--trace-symbol=sqlite3_open_v2 "-Wl,-Map,${CMAKE_CURRENT_BINARY_DIR}/product-link.map")
if(CMAKE_BUILD_TYPE STREQUAL "Debug")
  target_compile_definitions(exreader_product PRIVATE READER_PRODUCT_FIXTURES=1)
endif()

if(EXR_HOST_SYNC)
  list(APPEND CMAKE_PREFIX_PATH "${EXR_DAV}" "${EXR_SIDELOAD}")
  find_package(EXReaderSession 0.1.0 EXACT CONFIG REQUIRED)
  find_package(EXReaderSideload CONFIG REQUIRED)
  target_sources(exreader_product PRIVATE sync_jni.cpp)
  target_link_libraries(exreader_product PRIVATE EXReaderSession::reader_session)
  target_compile_definitions(exreader_host PRIVATE READER_HOST_SYNC=1)
  # The existing shared SDK also serves exreader-jni. Consume the installed
  # public sideload archive without adding its static SDK dependency closure.
  target_include_directories(exreader_host PRIVATE
    $<TARGET_PROPERTY:EXReaderSideload::exr_sideload,INTERFACE_INCLUDE_DIRECTORIES>)
  target_link_libraries(exreader_host PRIVATE $<TARGET_FILE:EXReaderSideload::exr_sideload> dl)
  target_link_options(exreader_host PRIVATE -Wl,--exclude-libs,ALL
    "-Wl,-Map,${CMAKE_CURRENT_BINARY_DIR}/sdk-host-link.map")
endif()
