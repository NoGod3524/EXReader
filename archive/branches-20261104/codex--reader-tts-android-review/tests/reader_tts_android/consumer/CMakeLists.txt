# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(EXReaderTTSAndroidConsumer LANGUAGES C CXX)
find_package(EXReaderTTSAndroid CONFIG REQUIRED NO_CMAKE_FIND_ROOT_PATH)
add_library(tts-consumer SHARED consumer.c bridge.cpp)
target_compile_features(tts-consumer PRIVATE c_std_11 cxx_std_17)
set_target_properties(tts-consumer PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON C_EXTENSIONS OFF)
target_compile_options(tts-consumer PRIVATE -Wall -Wextra -Werror)
target_link_libraries(tts-consumer PRIVATE EXReaderTTSAndroid::reader_tts)
