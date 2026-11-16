# SPDX-License-Identifier: MIT
# Opt in from the SDK tree without changing engine build/test registration:
# cmake -S . -B build -DCMAKE_PROJECT_EXReader_INCLUDE=<absolute path to this file>
if(WIN32 AND PROJECT_NAME STREQUAL "EXReader")
  enable_language(CXX)
  function(exr_add_selection_tests)
    # Current production shell, kept separate from the console test entry.
    add_executable(EXReaderAudit WIN32
      "${CMAKE_CURRENT_SOURCE_DIR}/examples/reader.c"
      "${CMAKE_CURRENT_SOURCE_DIR}/examples/windows/shell_d2d.cpp"
      "${CMAKE_CURRENT_SOURCE_DIR}/examples/windows/shell_speech.cpp"
      "${CMAKE_CURRENT_SOURCE_DIR}/examples/windows/shell_epub.cpp")
    target_compile_definitions(EXReaderAudit PRIVATE EXR_READER_WINDOWS_SHELL=1)
    target_compile_features(EXReaderAudit PRIVATE cxx_std_17)
    target_link_libraries(EXReaderAudit PRIVATE exreader miniz expat d2d1 dwrite
      gdi32 comdlg32 comctl32 shell32 ole32 oleaut32 uuid uiautomationcore advapi32 winhttp crypt32)
    if(MSVC)
      target_compile_options(EXReaderAudit PRIVATE /utf-8)
    else()
      target_link_libraries(EXReaderAudit PRIVATE m)
    endif()
    add_executable(exreader-shell-selection-test
      "${CMAKE_CURRENT_SOURCE_DIR}/examples/windows/check_shell_selection.c"
      "${CMAKE_CURRENT_SOURCE_DIR}/examples/windows/shell_d2d.cpp"
      "${CMAKE_CURRENT_SOURCE_DIR}/examples/windows/shell_speech.cpp"
      "${CMAKE_CURRENT_SOURCE_DIR}/examples/windows/shell_epub.cpp")
    target_compile_definitions(exreader-shell-selection-test PRIVATE EXR_READER_WINDOWS_SHELL=1)
    target_compile_features(exreader-shell-selection-test PRIVATE cxx_std_17)
    target_include_directories(exreader-shell-selection-test PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/include")
    target_link_libraries(exreader-shell-selection-test PRIVATE exreader miniz expat d2d1 dwrite
      gdi32 comdlg32 comctl32 shell32 ole32 oleaut32 uuid uiautomationcore advapi32 winhttp ws2_32 crypt32 psapi)
    if(MSVC)
      target_compile_options(exreader-shell-selection-test PRIVATE /UNDEBUG /utf-8)
    else()
      target_compile_options(exreader-shell-selection-test PRIVATE -UNDEBUG -Wall -Wextra -Werror)
      target_link_libraries(exreader-shell-selection-test PRIVATE m)
    endif()
    # These console entries never enter reader_WinMain or create an HWND.
    add_executable(check_sync
      "${CMAKE_CURRENT_SOURCE_DIR}/examples/windows/check_sync.c"
      "${CMAKE_CURRENT_SOURCE_DIR}/examples/windows/shell_d2d.cpp"
      "${CMAKE_CURRENT_SOURCE_DIR}/examples/windows/shell_speech.cpp"
      "${CMAKE_CURRENT_SOURCE_DIR}/examples/windows/shell_epub.cpp")
    target_compile_definitions(check_sync PRIVATE EXR_READER_WINDOWS_SHELL=1)
    target_compile_features(check_sync PRIVATE cxx_std_17)
    target_include_directories(check_sync PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/include")
    target_link_libraries(check_sync PRIVATE exreader miniz expat d2d1 dwrite
      gdi32 comdlg32 comctl32 shell32 ole32 oleaut32 uuid uiautomationcore advapi32 winhttp ws2_32 crypt32
      secur32 userenv)
    if(MSVC)
      target_compile_options(check_sync PRIVATE /UNDEBUG /utf-8)
    else()
      target_compile_options(check_sync PRIVATE -UNDEBUG -Wall -Wextra -Werror)
      target_link_libraries(check_sync PRIVATE m)
    endif()
    add_test(NAME windows-selection-sync COMMAND check_sync)
    add_test(NAME windows-privacy-cleanup COMMAND check_sync --privacy)
    set_tests_properties(windows-selection-sync PROPERTIES TIMEOUT 90 LABELS "headless")
    add_executable(check_shell_opds "${CMAKE_CURRENT_SOURCE_DIR}/examples/windows/check_shell_opds.c")
    target_link_libraries(check_shell_opds PRIVATE exreader winhttp ws2_32)
    if(MSVC)
      target_compile_options(check_shell_opds PRIVATE /utf-8)
    else()
      target_compile_options(check_shell_opds PRIVATE -Wall -Wextra -Werror)
    endif()
    add_test(NAME windows-opds-timeout COMMAND check_shell_opds --timeout-only "${CMAKE_CURRENT_BINARY_DIR}/opds-timeout")
    set_tests_properties(windows-opds-timeout PROPERTIES TIMEOUT 15 LABELS "headless")
    find_package(Python3 REQUIRED COMPONENTS Interpreter)
    add_test(NAME windows-render-budget-report-contract COMMAND ${Python3_EXECUTABLE}
      "${CMAKE_CURRENT_SOURCE_DIR}/tests/reader_perf_windows/render_budget.py" --self-check)
    add_test(NAME windows-a11y-control-contract COMMAND ${Python3_EXECUTABLE}
      "${CMAKE_CURRENT_SOURCE_DIR}/tests/reader_a11y_windows/control_contract.py")
    add_test(NAME windows-a11y-shell-capture-gate COMMAND ${Python3_EXECUTABLE}
      "${CMAKE_CURRENT_SOURCE_DIR}/tests/reader_a11y_windows/capture_shell.py" --self-check)
    add_test(NAME windows-a11y-control-inventory COMMAND ${Python3_EXECUTABLE}
      "${CMAKE_CURRENT_SOURCE_DIR}/tests/reader_a11y_windows/inventory_controls.py"
      --out "${CMAKE_CURRENT_BINARY_DIR}/control-inventory.json")
    add_test(NAME windows-a11y-c2-static COMMAND ${Python3_EXECUTABLE}
      "${CMAKE_CURRENT_SOURCE_DIR}/docs/ui/acceptance/check_a11y_c2.py"
      --out "${CMAKE_CURRENT_BINARY_DIR}/a11y-c2-static")
    set_tests_properties(windows-a11y-c2-static PROPERTIES LABELS "headless")
    # This hidden-HWND DirectWrite/D2D editor still uses desktop resources.
    # Isolate it like the selection tests; keep its timeout/assertions intact.
    if(TEST native-docx-footnotes-ui)
      set_tests_properties(native-docx-footnotes-ui PROPERTIES RUN_SERIAL TRUE)
    endif()
    foreach(group boundaries copy keyboard raster generated annotations shelf style shelfmeta shelf-budget dictionary-storage render-budget)
      add_test(NAME windows-selection-${group} COMMAND exreader-shell-selection-test ${group}
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/fonts/primary.ttf")
      set_tests_properties(windows-selection-${group} PROPERTIES RUN_SERIAL TRUE)
    endforeach()
  endfunction()
  cmake_language(DEFER CALL exr_add_selection_tests)
endif()
