cmake_minimum_required(VERSION 3.24)
project(WindowsRawPeerOwner LANGUAGES C CXX)
if(NOT WIN32)
  message(FATAL_ERROR "This consumer executes the real Windows records owner")
endif()
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
set(EXR_SDK "" CACHE PATH "Installed SDK 3.41.0")
find_package(EXReader 3.41.0 EXACT CONFIG REQUIRED COMPONENTS core library
  PATHS "${EXR_SDK}" NO_DEFAULT_PATH)
find_package(EXReaderProductCatalog 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderRevisions 0.4.0 EXACT CONFIG REQUIRED)
foreach(_package Commands DesktopMetadata ReadingState ReadingCommands AnnotationView Sync Session)
  find_package(EXReader${_package} 0.2.0 EXACT CONFIG REQUIRED)
endforeach()
get_filename_component(_root "${CMAKE_CURRENT_SOURCE_DIR}/../../.." ABSOLUTE)
set(_owner "${_root}/apps/reader/desktop/windows_records_owner.cpp")
file(SHA256 "${_owner}" _owner_sha)
execute_process(COMMAND git rev-parse HEAD WORKING_DIRECTORY "${_root}"
  OUTPUT_VARIABLE _source_sha OUTPUT_STRIP_TRAILING_WHITESPACE COMMAND_ERROR_IS_FATAL ANY)
add_executable(windows-peer-owner probe.cpp "${_owner}")
target_include_directories(windows-peer-owner PRIVATE "${_root}/apps/reader/desktop")
target_compile_definitions(windows-peer-owner PRIVATE _CRT_SECURE_NO_WARNINGS
  "PROBE_SOURCE_SHA=\"${_source_sha}\"" "PROBE_OWNER_SHA=\"${_owner_sha}\"")
target_compile_definitions(windows-peer-owner PRIVATE EXR_READER_WINDOWS_RAW3=1)
target_link_libraries(windows-peer-owner PRIVATE
  EXReaderDesktopMetadata::reader_desktop_metadata
  EXReaderCommands::reader_commands
  EXReaderSession::reader_session EXReaderSync::reader_sync
  EXReaderAnnotationView::reader_annotation_view
  EXReaderReadingCommands::reader_reading_commands
  EXReaderReadingState::reader_reading_state
  EXReaderRevisions::reader_revisions
  EXReaderProductCatalog::reader_catalog EXReaderProductCatalog::reader_catalog_sqlite
  EXReader::exr_library EXReader::exr_core bcrypt)
if(MSVC)
  target_compile_options(windows-peer-owner PRIVATE /W4 /EHsc)
  target_link_options(windows-peer-owner PRIVATE "/MAP:${CMAKE_CURRENT_BINARY_DIR}/windows-peer-owner.map")
endif()
