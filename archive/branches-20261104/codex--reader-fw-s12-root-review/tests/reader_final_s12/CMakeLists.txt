# SPDX-License-Identifier: MIT
# S12 independent installed consumers. Consumes only installed public packages;
# never a build-tree include directory, private header or second SQLite build.
cmake_minimum_required(VERSION 3.24)
project(ReaderFinalS12Consumers LANGUAGES C CXX)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8 /W4)
else()
  add_compile_options(-Wall -Wextra)
endif()

# The explicit raw-capability metadata family plus the unchanged account package.
find_package(EXReaderProductCatalog 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderRevisions 0.4.0 EXACT CONFIG REQUIRED)
find_package(EXReaderCommands 0.2.0 EXACT CONFIG REQUIRED)
find_package(EXReaderDesktopMetadata 0.2.0 EXACT CONFIG REQUIRED)
find_package(EXReaderAccountProfiles 0.1.0 EXACT CONFIG REQUIRED)

add_executable(s12-consumer probe.cpp)
target_link_libraries(s12-consumer PRIVATE
  EXReaderDesktopMetadata::reader_desktop_metadata
  EXReaderCommands::reader_commands
  EXReaderRevisions::reader_revisions
  EXReaderProductCatalog::reader_catalog
  EXReaderProductCatalog::reader_catalog_sqlite
  EXReaderAccountProfiles::reader_account_profiles)
if(MSVC)
  target_link_options(s12-consumer PRIVATE "/MAP:${CMAKE_CURRENT_BINARY_DIR}/s12-consumer.map")
elseif(APPLE)
  target_link_options(s12-consumer PRIVATE "-Wl,-map,${CMAKE_CURRENT_BINARY_DIR}/s12-consumer.map")
else()
  target_link_options(s12-consumer PRIVATE "-Wl,-Map=${CMAKE_CURRENT_BINARY_DIR}/s12-consumer.map")
endif()

# The same observable values through the installed C ABI header only.
add_executable(s12-c-consumer api.c)
set_target_properties(s12-c-consumer PROPERTIES LINKER_LANGUAGE CXX)
target_link_libraries(s12-c-consumer PRIVATE
  EXReaderCommands::reader_commands
  EXReaderProductCatalog::reader_catalog
  EXReaderProductCatalog::reader_catalog_sqlite)
if(MSVC)
  target_link_options(s12-c-consumer PRIVATE "/MAP:${CMAKE_CURRENT_BINARY_DIR}/s12-c-consumer.map")
elseif(APPLE)
  target_link_options(s12-c-consumer PRIVATE "-Wl,-map,${CMAKE_CURRENT_BINARY_DIR}/s12-c-consumer.map")
else()
  target_link_options(s12-c-consumer PRIVATE "-Wl,-Map=${CMAKE_CURRENT_BINARY_DIR}/s12-c-consumer.map")
endif()
