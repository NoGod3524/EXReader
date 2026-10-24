# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(ReaderWebDAVInteropConsumer LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
# Installed packages only: the same EXReaderSync/Revisions/WebDAV and the one
# product SQLite they already bind. No module source is compiled here.
find_package(EXReaderSync 0.1.0 EXACT CONFIG REQUIRED)
add_executable(interop-consumer main.cpp)
target_link_libraries(interop-consumer PRIVATE EXReaderSync::reader_sync)
target_compile_options(interop-consumer PRIVATE -Wall -Wextra -Werror)
