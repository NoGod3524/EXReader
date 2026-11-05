cmake_minimum_required(VERSION 3.24)
project(GtkStalePreviewWriter LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
find_package(EXReaderDesktopMetadata 0.1.0 EXACT CONFIG REQUIRED)
add_executable(gtk-preview-writer main.cpp)
target_link_libraries(gtk-preview-writer PRIVATE EXReaderDesktopMetadata::reader_desktop_metadata)

file(GENERATE OUTPUT "${CMAKE_BINARY_DIR}/linked-modules.txt" CONTENT "${EXReaderDesktopMetadata_DIR}\n$<TARGET_FILE:EXReaderDesktopMetadata::reader_desktop_metadata>\n$<TARGET_FILE:EXReaderCommands::reader_commands>\n$<TARGET_FILE:EXReaderRevisions::reader_revisions>\n")
