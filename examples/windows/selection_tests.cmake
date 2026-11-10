# SPDX-License-Identifier: MIT
# Opt in from the SDK tree without changing engine build/test registration:
# cmake -S . -B build -DCMAKE_PROJECT_EXReader_INCLUDE=<absolute path to this file>
if(WIN32 AND PROJECT_NAME STREQUAL "EXReader")
  option(EXR_WINDOWS_WINDOW_TESTS "Register legacy tests that create HWNDs" OFF)
  enable_language(CXX)
  function(exr_add_selection_tests)
    if(EXR_WINDOWS_WINDOW_TESTS)
      add_executable(exreader-shell-selection-test
        "${CMAKE_CURRENT_SOURCE_DIR}/examples/windows/check_shell_selection.c"
        "${CMAKE_CURRENT_SOURCE_DIR}/examples/windows/shell_d2d.cpp"
        "${CMAKE_CURRENT_SOURCE_DIR}/examples/windows/shell_speech.cpp"
        "${CMAKE_CURRENT_SOURCE_DIR}/examples/windows/shell_epub.cpp")
      target_compile_definitions(exreader-shell-selection-test PRIVATE EXR_READER_WINDOWS_SHELL=1)
      target_compile_features(exreader-shell-selection-test PRIVATE cxx_std_17)
      target_include_directories(exreader-shell-selection-test PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/include")
      target_link_libraries(exreader-shell-selection-test PRIVATE exreader miniz expat d2d1 dwrite
        gdi32 comdlg32 shell32 ole32 oleaut32 uuid uiautomationcore advapi32 winhttp crypt32)
      if(MSVC)
        target_compile_options(exreader-shell-selection-test PRIVATE /UNDEBUG /utf-8)
      else()
        target_compile_options(exreader-shell-selection-test PRIVATE -UNDEBUG -Wall -Wextra -Werror)
        target_link_libraries(exreader-shell-selection-test PRIVATE m)
      endif()
    endif()
    add_executable(check_sync
      "${CMAKE_CURRENT_SOURCE_DIR}/examples/windows/check_sync.c"
      "${CMAKE_CURRENT_SOURCE_DIR}/examples/windows/shell_d2d.cpp"
      "${CMAKE_CURRENT_SOURCE_DIR}/examples/windows/shell_speech.cpp"
      "${CMAKE_CURRENT_SOURCE_DIR}/examples/windows/shell_epub.cpp")
    target_compile_definitions(check_sync PRIVATE EXR_READER_WINDOWS_SHELL=1)
    target_compile_features(check_sync PRIVATE cxx_std_17)
    target_include_directories(check_sync PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/include")
    target_link_libraries(check_sync PRIVATE exreader miniz expat d2d1 dwrite gdi32
      comdlg32 shell32 ole32 oleaut32 uuid uiautomationcore advapi32 winhttp ws2_32 crypt32)
    if(MSVC)
      target_compile_options(check_sync PRIVATE /UNDEBUG /utf-8)
    else()
      target_compile_options(check_sync PRIVATE -UNDEBUG -Wall -Wextra -Werror)
      target_link_libraries(check_sync PRIVATE m)
    endif()
    add_test(NAME windows-selection-sync COMMAND check_sync)
    set_tests_properties(windows-selection-sync PROPERTIES TIMEOUT 120 RUN_SERIAL TRUE LABELS "headless")
    add_executable(check_shell_opds "${CMAKE_CURRENT_SOURCE_DIR}/examples/windows/check_shell_opds.c")
    target_link_libraries(check_shell_opds PRIVATE exreader winhttp ws2_32)
    if(MSVC)
      target_compile_options(check_shell_opds PRIVATE /W4 /WX /utf-8)
    else()
      target_compile_options(check_shell_opds PRIVATE -Wall -Wextra -Werror)
    endif()
    add_test(NAME windows-opds-timeout COMMAND check_shell_opds --timeout-test "${CMAKE_CURRENT_BINARY_DIR}/opds-timeout")
    set_tests_properties(windows-opds-timeout PROPERTIES TIMEOUT 15 LABELS "headless")
    find_package(Python3 REQUIRED COMPONENTS Interpreter)
    add_test(NAME windows-a11y-static COMMAND "${Python3_EXECUTABLE}"
      "${CMAKE_CURRENT_SOURCE_DIR}/docs/ui/acceptance/check_a11y_c2.py"
      --output "${CMAKE_CURRENT_BINARY_DIR}/c2-static.json")
    add_test(NAME windows-a11y-static-negative COMMAND "${Python3_EXECUTABLE}"
      "${CMAKE_CURRENT_SOURCE_DIR}/docs/ui/acceptance/check_a11y_c2.py" --self-test)
    set_tests_properties(windows-a11y-static windows-a11y-static-negative PROPERTIES LABELS "headless" TIMEOUT 60)
    if(EXR_WINDOWS_WINDOW_TESTS)
      foreach(group boundaries copy keyboard raster generated annotations shelf style shelfmeta dictionary-storage)
        add_test(NAME windows-selection-${group} COMMAND exreader-shell-selection-test ${group}
          "${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/fonts/primary.ttf")
        set_tests_properties(windows-selection-${group} PROPERTIES RUN_SERIAL TRUE)
      endforeach()
    endif()
  endfunction()
  cmake_language(DEFER CALL exr_add_selection_tests)
endif()
