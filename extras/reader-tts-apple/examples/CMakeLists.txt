# SPDX-License-Identifier: MIT
# Installed-package consumer example: nothing here reads the module source tree,
# it only uses the exported package and the installed header/library.
cmake_minimum_required(VERSION 3.22)
project(EXReaderTTSAppleExample LANGUAGES C CXX OBJCXX)

find_package(EXReaderTTSApple 0.1.0 CONFIG REQUIRED)

add_executable(reader_tts_example reader_tts_example.mm)
target_compile_features(reader_tts_example PRIVATE cxx_std_17)
target_compile_options(reader_tts_example PRIVATE -Wall -Wextra -Werror -fobjc-arc)
target_link_libraries(reader_tts_example PRIVATE EXReaderTTSApple::reader_tts)
