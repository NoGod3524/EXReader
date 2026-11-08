# SPDX-License-Identifier: MIT
# Opt in from the SDK tree without changing engine build/test registration:
# cmake -S . -B build -DCMAKE_PROJECT_EXReader_INCLUDE=<absolute path to this file>
if(WIN32 AND PROJECT_NAME STREQUAL "EXReader")
  enable_language(CXX)
  function(exr_add_selection_tests)
    add_executable(exreader-shell-selection-test
      "${CMAKE_CURRENT_SOURCE_DIR}/examples/windows/check_shell_selection.c"
      "${CMAKE_CURRENT_SOURCE_DIR}/examples/windows/shell_d2d.cpp"
      "${CMAKE_CURRENT_SOURCE_DIR}/examples/windows/shell_speech.cpp"
      "${CMAKE_CURRENT_SOURCE_DIR}/examples/windows/shell_epub.cpp")
    target_compile_definitions(exreader-shell-selection-test PRIVATE EXR_READER_WINDOWS_SHELL=1)
    target_compile_features(exreader-shell-selection-test PRIVATE cxx_std_17)
    target_include_directories(exreader-shell-selection-test PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/include")
    target_link_libraries(exreader-shell-selection-test PRIVATE exreader miniz expat d2d1 dwrite
      gdi32 comdlg32 shell32 ole32 oleaut32 uuid uiautomationcore advapi32)
    if(MSVC)
      target_compile_options(exreader-shell-selection-test PRIVATE /UNDEBUG /utf-8)
    else()
      target_compile_options(exreader-shell-selection-test PRIVATE -UNDEBUG -Wall -Wextra -Werror)
      target_link_libraries(exreader-shell-selection-test PRIVATE m)
    endif()
    foreach(group boundaries copy keyboard raster generated annotations)
      add_test(NAME windows-selection-${group} COMMAND exreader-shell-selection-test ${group}
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/fonts/primary.ttf")
      set_tests_properties(windows-selection-${group} PROPERTIES RUN_SERIAL TRUE)
    endforeach()
  endfunction()
  cmake_language(DEFER CALL exr_add_selection_tests)
endif()
