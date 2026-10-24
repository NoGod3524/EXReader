# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(EXReaderOpdsBrowser VERSION 0.1.0 LANGUAGES C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()

# The frozen OPDS module (extras/opds, protected tree) has no install or export rule.
# Its unchanged sources are compiled into this package's archive so an installed
# consumer links exactly one library; this package adds no parser of its own.
set(READER_OPDS_MODULE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../../extras/opds"
    CACHE PATH "Frozen OPDS module directory (extras/opds)")

add_library(reader_opds_browser STATIC
  src/browser.c
  src/transport.c
  "${READER_OPDS_MODULE_DIR}/src/opds_core.c"
  "${READER_OPDS_MODULE_DIR}/src/opds_xml.c"
  "${READER_OPDS_MODULE_DIR}/src/opds_feed.c"
  "${READER_OPDS_MODULE_DIR}/src/opds_net.c"
  "${READER_OPDS_MODULE_DIR}/src/opds_fs.c"
  "${READER_OPDS_MODULE_DIR}/src/opds_client.c")
target_include_directories(reader_opds_browser
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<BUILD_INTERFACE:${READER_OPDS_MODULE_DIR}/include>
    $<INSTALL_INTERFACE:include>
  PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src)

option(READER_OPDS_TLS "Build an https transport (WinHTTP on Windows, libcurl elsewhere)" ON)
set(READER_OPDS_TLS_ENABLED 0)
set(READER_OPDS_CURL 0)
if(READER_OPDS_TLS)
  if(WIN32)
    target_sources(reader_opds_browser PRIVATE src/tls_winhttp.c)
    set(READER_OPDS_TLS_ENABLED 1)
  else()
    find_package(CURL QUIET)
    if(NOT CURL_FOUND AND APPLE)
      execute_process(COMMAND xcrun --show-sdk-path OUTPUT_VARIABLE _exr_sdk_path OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
      find_path(READER_OPDS_CURL_INCLUDE curl/curl.h PATHS "${_exr_sdk_path}/usr/include" NO_DEFAULT_PATH)
      find_library(READER_OPDS_CURL_LIBRARY curl PATHS "${_exr_sdk_path}/usr/lib" NO_DEFAULT_PATH)
      if(READER_OPDS_CURL_INCLUDE AND READER_OPDS_CURL_LIBRARY)
        set(CURL_FOUND TRUE)
      endif()
    endif()
    if(CURL_FOUND)
      target_sources(reader_opds_browser PRIVATE src/tls_curl.c)
      if(TARGET CURL::libcurl)
        target_link_libraries(reader_opds_browser PUBLIC CURL::libcurl)
        set(READER_OPDS_CURL 1)
      else()
        target_include_directories(reader_opds_browser PRIVATE "${READER_OPDS_CURL_INCLUDE}")
        target_link_libraries(reader_opds_browser PUBLIC "${READER_OPDS_CURL_LIBRARY}")
      endif()
      set(READER_OPDS_TLS_ENABLED 1)
    else()
      message(WARNING "libcurl not found: no https transport is built and https URLs return NEEDS_HOST")
    endif()
  endif()
endif()
target_compile_definitions(reader_opds_browser PRIVATE READER_OPDS_TLS=${READER_OPDS_TLS_ENABLED})

if(WIN32)
  target_link_libraries(reader_opds_browser PUBLIC ws2_32 winhttp bcrypt)
endif()
if(NOT MSVC)
  target_compile_options(reader_opds_browser PRIVATE -Wall -Wextra -Wno-unused-parameter)
endif()

# SDK-owner phase: only the installed public SDK library and the installed sideload
# package are used. Without them the network phase still builds and installs.
option(READER_OPDS_SDK "Build the SDK-owner import phase" ON)
option(READER_OPDS_BUILD_EXAMPLE "Build the in-tree consumer example" OFF)
set(READER_OPDS_HAVE_IMPORT 0)
if(READER_OPDS_SDK)
  if(EXR_SDK)
    list(PREPEND CMAKE_PREFIX_PATH "${EXR_SDK}")
  endif()
  find_package(EXReader CONFIG QUIET COMPONENTS library)
  find_package(EXReaderSideload CONFIG QUIET)
  if(EXReader_library_FOUND AND EXReaderSideload_FOUND)
    add_library(reader_opds_import STATIC src/import.c)
    target_include_directories(reader_opds_import
      PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include> $<INSTALL_INTERFACE:include>)
    target_link_libraries(reader_opds_import PUBLIC reader_opds_browser EXReader::exr_library EXReaderSideload::exr_sideload)
    set(READER_OPDS_HAVE_IMPORT 1)
  else()
    message(WARNING "EXReader library / EXReaderSideload packages are missing: the import phase is not built")
  endif()
endif()

if(READER_OPDS_BUILD_EXAMPLE)
  add_executable(reader-opds-example examples/reader_opds_consume.c)
  target_link_libraries(reader-opds-example PRIVATE reader_opds_browser)
endif()

include(CMakePackageConfigHelpers)
set(READER_OPDS_INSTALL_TARGETS reader_opds_browser)
if(READER_OPDS_HAVE_IMPORT)
  list(APPEND READER_OPDS_INSTALL_TARGETS reader_opds_import)
endif()
install(TARGETS ${READER_OPDS_INSTALL_TARGETS} EXPORT EXReaderOpdsBrowserTargets ARCHIVE DESTINATION lib)
install(FILES include/reader_opds_browser.h "${READER_OPDS_MODULE_DIR}/include/opds.h" DESTINATION include)
if(READER_OPDS_HAVE_IMPORT)
  install(FILES include/reader_opds_import.h DESTINATION include)
endif()
install(EXPORT EXReaderOpdsBrowserTargets NAMESPACE EXReaderOpdsBrowser:: DESTINATION lib/cmake/EXReaderOpdsBrowser)
configure_package_config_file(EXReaderOpdsBrowserConfig.cmake.in
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderOpdsBrowserConfig.cmake"
  INSTALL_DESTINATION lib/cmake/EXReaderOpdsBrowser)
write_basic_package_version_file("${CMAKE_CURRENT_BINARY_DIR}/EXReaderOpdsBrowserConfigVersion.cmake"
  VERSION ${PROJECT_VERSION} COMPATIBILITY SameMinorVersion)
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/EXReaderOpdsBrowserConfig.cmake"
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderOpdsBrowserConfigVersion.cmake"
  DESTINATION lib/cmake/EXReaderOpdsBrowser)
