cmake_minimum_required(VERSION 3.24)
project(ReaderFinalA LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 17)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
find_package(EXReaderRevisions CONFIG REQUIRED)
find_package(Python3 REQUIRED COMPONENTS Interpreter)
# Reuse the installed-package probe, including its externally observable crash gates.
add_executable(final-a-consumer ../reader_revisions/consumer/main.cpp)
target_link_libraries(final-a-consumer PRIVATE EXReaderRevisions::reader_revisions
  EXReaderProductCatalog::reader_catalog_sqlite)
if(WIN32)
  target_link_libraries(final-a-consumer PRIVATE shell32)
endif()
enable_testing()
foreach(scenario organization reconnect crash)
  add_test(NAME final-a-${scenario} COMMAND Python3::Interpreter
    "${CMAKE_CURRENT_SOURCE_DIR}/check_clients.py" --consumer $<TARGET_FILE:final-a-consumer>
    --scenario ${scenario})
  set_tests_properties(final-a-${scenario} PROPERTIES TIMEOUT 120)
endforeach()
