# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(ReaderIOSSessionInstalledConsumer LANGUAGES C CXX OBJCXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_OBJCXX_STANDARD 17)
find_package(EXReaderReadingState 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderSession 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderSideload CONFIG REQUIRED)
add_executable(ReaderSessionProbe MACOSX_BUNDLE ios_main.mm probe.cpp fault_consumer.cpp
  ../reader_reading_v2/consumer/api.c ../reader_session/consumer/api.c)
target_compile_options(ReaderSessionProbe PRIVATE $<$<COMPILE_LANGUAGE:OBJCXX>:-fobjc-arc>)
target_link_libraries(ReaderSessionProbe PRIVATE EXReaderReadingState::reader_reading_state
  EXReaderProductCatalog::reader_catalog EXReaderProductCatalog::reader_catalog_sqlite
  EXReaderSession::reader_session EXReaderSideload::exr_sideload "-framework UIKit")
target_link_options(ReaderSessionProbe PRIVATE "-Wl,-map,${CMAKE_CURRENT_BINARY_DIR}/session-link.map")
set_target_properties(ReaderSessionProbe PROPERTIES MACOSX_BUNDLE_INFO_PLIST "${CMAKE_CURRENT_SOURCE_DIR}/Info.plist")
add_executable(ios-session-controls fault_main.cpp fault_consumer.cpp ../reader_session/consumer/api.c)
set_target_properties(ios-session-controls PROPERTIES MACOSX_BUNDLE FALSE)
target_link_libraries(ios-session-controls PRIVATE EXReaderSession::reader_session)
add_executable(ios-session-revisions ../reader_revisions/consumer/main.cpp)
set_target_properties(ios-session-revisions PROPERTIES MACOSX_BUNDLE FALSE)
target_link_libraries(ios-session-revisions PRIVATE EXReaderRevisions::reader_revisions
  EXReaderProductCatalog::reader_catalog_sqlite)
