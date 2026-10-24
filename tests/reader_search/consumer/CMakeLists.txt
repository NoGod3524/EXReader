cmake_minimum_required(VERSION 3.24)
project(ReaderSearchInstalledConsumer LANGUAGES C CXX)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
# Installed packages only. The C consumer sees the optional search package and
# the frozen SDK; the C++ probe additionally uses the unchanged reading-state
# adapter to prove hits encode through reader_rs_encode_v2.
find_package(EXReaderSearch 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderReadingState 0.1.0 EXACT CONFIG REQUIRED)
add_executable(search-c-consumer api.c)
set_target_properties(search-c-consumer PROPERTIES LINKER_LANGUAGE CXX)
target_link_libraries(search-c-consumer PRIVATE EXReaderSearch::reader_search)
add_executable(search-probe probe.cpp peak.c)
target_link_libraries(search-probe PRIVATE EXReaderSearch::reader_search EXReaderReadingState::reader_reading_state
  EXReaderProductCatalog::reader_catalog EXReaderProductCatalog::reader_catalog_sqlite)
if(WIN32)
  target_link_libraries(search-probe PRIVATE psapi)
endif()
