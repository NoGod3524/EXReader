# SPDX-License-Identifier: MIT
# Fresh-directory composition consumer. Its only inputs are one installed
# prefix and find_package(): no source tree, no build tree, no sibling test
# helper, no SDK private header and no second SQLite build.
cmake_minimum_required(VERSION 3.24)
project(EXReaderModuleComposition LANGUAGES C CXX)
if(MSVC)
  # Every installed module is built with the static MSVC runtime; a consumer
  # that keeps the default /MD cannot link them, so state it here as well.
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()

if(NOT EXR_MODULE_PREFIX)
  message(FATAL_ERROR "EXR_MODULE_PREFIX must name the single installed prefix")
endif()
get_filename_component(EXR_MODULE_PREFIX "${EXR_MODULE_PREFIX}" ABSOLUTE)
list(PREPEND CMAKE_PREFIX_PATH "${EXR_MODULE_PREFIX}")

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# One prefix, every optional package, in dependency order.
find_package(EXReader 3.40.0 EXACT CONFIG REQUIRED COMPONENTS core library)
find_package(EXReaderProductCatalog 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderRevisions 0.3.0 EXACT CONFIG REQUIRED)
find_package(EXReaderWebDAV 0.2.0 EXACT CONFIG REQUIRED)
find_package(EXReaderSideload CONFIG REQUIRED)
find_package(EXReaderCredentials 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderSearch 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderPreferences 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderBatchImport 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderSync 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderCommands 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderDesktopMetadata 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderSession 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderReadingState 0.1.0 EXACT CONFIG REQUIRED)
find_package(Threads REQUIRED)

set(EXR_PACKAGE_TARGETS
  EXReader::exr_core
  EXReader::exr_library
  EXReaderProductCatalog::reader_catalog
  EXReaderProductCatalog::reader_catalog_sqlite
  EXReaderRevisions::reader_revisions
  EXReaderRevisions::reader_revision_hash
  EXReaderWebDAV::exr_webdav
  EXReaderSideload::exr_sideload
  EXReaderCredentials::exr_credentials
  EXReaderSearch::reader_search
  EXReaderPreferences::reader_preferences
  EXReaderBatchImport::reader_batch_import
  EXReaderSync::reader_sync
  EXReaderCommands::reader_commands
  EXReaderDesktopMetadata::reader_desktop_metadata
  EXReaderSession::reader_session
  EXReaderReadingState::reader_reading_state)

foreach(target IN LISTS EXR_PACKAGE_TARGETS)
  if(NOT TARGET ${target})
    message(FATAL_ERROR "the installed prefix does not export ${target}")
  endif()
endforeach()

# The composed link graph: the C11 consumer and the C++17 consumer both link
# every installed package from this one prefix.
set(EXR_COMPOSED_LIBRARIES
  EXReaderReadingState::reader_reading_state
  EXReaderSync::reader_sync
  EXReaderSession::reader_session
  EXReaderDesktopMetadata::reader_desktop_metadata
  EXReaderCommands::reader_commands
  EXReaderSearch::reader_search
  EXReaderBatchImport::reader_batch_import
  EXReaderPreferences::reader_preferences
  EXReaderCredentials::exr_credentials
  EXReaderSideload::exr_sideload
  EXReaderWebDAV::exr_webdav
  EXReaderRevisions::reader_revisions
  EXReaderProductCatalog::reader_catalog
  EXReaderProductCatalog::reader_catalog_sqlite
  EXReader::exr_library
  EXReader::exr_core
  EXReader::exr_base
  Threads::Threads)

add_executable(composition-c composition_c.c)
target_link_libraries(composition-c PRIVATE ${EXR_COMPOSED_LIBRARIES})
set_target_properties(composition-c PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON LINKER_LANGUAGE CXX)

add_executable(composition-cxx composition_probe.cpp)
target_link_libraries(composition-cxx PRIVATE ${EXR_COMPOSED_LIBRARIES})
set_target_properties(composition-cxx PROPERTIES CXX_STANDARD 17 CXX_STANDARD_REQUIRED ON)

# A GNU link map plus a symbol trace of the product SQLite entry point; MSVC
# writes the map through /MAP. The judge reads them for provider counting.
if(MSVC)
  target_link_options(composition-cxx PRIVATE "/MAP:${CMAKE_CURRENT_BINARY_DIR}/composition-link.map")
  target_link_options(composition-c PRIVATE "/MAP:${CMAKE_CURRENT_BINARY_DIR}/composition-c-link.map")
elseif(APPLE)
  # ld64 spells the map flag in lower case and has no --trace-symbol.
  target_link_options(composition-cxx PRIVATE "-Wl,-map,${CMAKE_CURRENT_BINARY_DIR}/composition-link.map")
  target_link_options(composition-c PRIVATE "-Wl,-map,${CMAKE_CURRENT_BINARY_DIR}/composition-c-link.map")
else()
  target_link_options(composition-cxx PRIVATE
    "-Wl,-Map,${CMAKE_CURRENT_BINARY_DIR}/composition-link.map" "-Wl,--trace-symbol=sqlite3_open_v2")
  target_link_options(composition-c PRIVATE "-Wl,-Map,${CMAKE_CURRENT_BINARY_DIR}/composition-c-link.map")
endif()

# Negative control: a second SQLite provider in the same link graph must be
# refused. A directly linked object file always collides, on every linker.
if(EXR_NEGATIVE_DUPLICATE_PROVIDER)
  add_library(second_sqlite_provider OBJECT duplicate_provider.c)
  target_link_libraries(composition-cxx PRIVATE $<TARGET_OBJECTS:second_sqlite_provider>)
endif()

# Per-header self-containment: one translation unit per installed public
# header, compiled in C11 and C++17 against its own owning package only, so a
# missing exported include directory or forgotten public dependency fails.
function(exr_header_probe owner header language)
  string(MAKE_C_IDENTIFIER "${header}" slug)
  if(language STREQUAL "CXX")
    set(probe "${CMAKE_CURRENT_BINARY_DIR}/probe/${slug}.cpp")
    file(WRITE "${probe}" "#include <${header}>\n")
    add_library(header-${slug}-cxx OBJECT "${probe}")
    set_target_properties(header-${slug}-cxx PROPERTIES CXX_STANDARD 17 CXX_STANDARD_REQUIRED ON)
    target_link_libraries(header-${slug}-cxx PRIVATE ${owner})
  else()
    set(probe "${CMAKE_CURRENT_BINARY_DIR}/probe/${slug}.c")
    file(WRITE "${probe}" "#include <${header}>\n")
    add_library(header-${slug}-c OBJECT "${probe}")
    set_target_properties(header-${slug}-c PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON)
    target_link_libraries(header-${slug}-c PRIVATE ${owner})
  endif()
endfunction()

set(EXR_MODULE_HEADERS
  "EXReader::exr_core|exreader.h"
  "EXReaderProductCatalog::reader_catalog|catalog.h"
  "EXReaderProductCatalog::reader_catalog_sqlite|sqlite3.h"
  "EXReaderRevisions::reader_revisions|reader_revisions.h"
  "EXReaderRevisions::reader_revisions|reader_projection.h"
  "EXReaderCommands::reader_commands|reader_commands.h"
  "EXReaderDesktopMetadata::reader_desktop_metadata|reader_metadata.h"
  "EXReaderReadingState::reader_reading_state|reader_reading_state.h"
  "EXReaderSearch::reader_search|reader_search.h"
  "EXReaderSession::reader_session|reader_session.h"
  "EXReaderSync::reader_sync|reader_sync.h"
  "EXReaderPreferences::reader_preferences|reader_preferences.h"
  "EXReaderBatchImport::reader_batch_import|reader_batch_import.h"
  "EXReaderSideload::exr_sideload|exr_sideload.h"
  "EXReaderWebDAV::exr_webdav|exr_webdav.h"
  "EXReaderCredentials::exr_credentials|exr_credentials.h")

foreach(entry IN LISTS EXR_MODULE_HEADERS)
  string(REPLACE "|" ";" pair "${entry}")
  list(GET pair 0 owner)
  list(GET pair 1 header)
  exr_header_probe("${owner}" "${header}" "C")
  exr_header_probe("${owner}" "${header}" "CXX")
endforeach()

file(GLOB exr_sdk_headers RELATIVE "${EXR_MODULE_PREFIX}/include" "${EXR_MODULE_PREFIX}/include/exr/*.h")
list(SORT exr_sdk_headers)
foreach(header IN LISTS exr_sdk_headers)
  # RELATIVE yields "exr/<name>.h", which is exactly the include spelling.
  exr_header_probe("EXReader::exr_core" "${header}" "C")
  exr_header_probe("EXReader::exr_core" "${header}" "CXX")
endforeach()

# Configuration-time snapshot of every imported target's usage requirements.
# check_prefix.py rejects an include directory outside the installed prefix,
# which is how a leaked source-tree include is caught.
function(exr_json_string value out)
  string(REPLACE "\\" "\\\\" value "${value}")
  string(REPLACE "\"" "\\\"" value "${value}")
  set(${out} "\"${value}\"" PARENT_SCOPE)
endfunction()

set(exr_interface_json "{\n  \"prefix\": ")
exr_json_string("${EXR_MODULE_PREFIX}" quoted_prefix)
string(APPEND exr_interface_json "${quoted_prefix},\n  \"targets\": [\n")
set(exr_first_target TRUE)
foreach(target IN LISTS EXR_PACKAGE_TARGETS)
  get_target_property(includes ${target} INTERFACE_INCLUDE_DIRECTORIES)
  if(NOT includes)
    set(includes "")
  endif()
  set(include_json "")
  set(exr_first_include TRUE)
  foreach(directory IN LISTS includes)
    if(exr_first_include)
      set(exr_first_include FALSE)
    else()
      string(APPEND include_json ", ")
    endif()
    exr_json_string("${directory}" quoted)
    string(APPEND include_json "${quoted}")
  endforeach()
  get_target_property(links ${target} INTERFACE_LINK_LIBRARIES)
  if(NOT links)
    set(links "")
  endif()
  set(link_json "")
  set(exr_first_link TRUE)
  foreach(link IN LISTS links)
    if(exr_first_link)
      set(exr_first_link FALSE)
    else()
      string(APPEND link_json ", ")
    endif()
    exr_json_string("${link}" quoted)
    string(APPEND link_json "${quoted}")
  endforeach()
  if(exr_first_target)
    set(exr_first_target FALSE)
  else()
    string(APPEND exr_interface_json ",\n")
  endif()
  exr_json_string("${target}" quoted_target)
  string(APPEND exr_interface_json "    {\"target\": ${quoted_target}, \"includes\": [${include_json}], \"links\": [${link_json}]}")
endforeach()
string(APPEND exr_interface_json "\n  ]\n}\n")
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/composition-interface.json" "${exr_interface_json}")
