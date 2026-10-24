cmake_minimum_required(VERSION 3.24)
project(EXReaderDistributionProbe LANGUAGES C)
# Only the installed package is visible. The probe reads the installed public
# identity, and its link command is the recorded dependency edge for the whole
# installed SDK, so every distributed archive must appear on that line.
list(PREPEND CMAKE_PREFIX_PATH "${EXR_SDK}")
find_package(EXReader 3.40.0 EXACT CONFIG REQUIRED COMPONENTS core pdf)
add_executable(probe probe.c)
target_link_libraries(probe PRIVATE EXReader::exreader EXReader::exr_pdf)
if(TARGET EXReader::exr_library)
  target_link_libraries(probe PRIVATE EXReader::exr_library)
endif()
set_target_properties(probe PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON)
if(MSVC)
  set_property(TARGET probe PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
endif()
