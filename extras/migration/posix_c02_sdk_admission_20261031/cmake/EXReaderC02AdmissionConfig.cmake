include(CMakeFindDependencyMacro)
find_dependency(EXReader 3.42.0 EXACT CONFIG COMPONENTS library)
get_filename_component(_pc02_prefix "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)
if(NOT TARGET EXReaderC02::Admission)
  add_library(EXReaderC02::Admission INTERFACE IMPORTED)
  set_target_properties(EXReaderC02::Admission PROPERTIES
    INTERFACE_INCLUDE_DIRECTORIES "${_pc02_prefix}/include/exreader-c02-admission"
    INTERFACE_LINK_LIBRARIES "${_pc02_prefix}/lib/libexreader-posix-c02-sdk-admission.a;${_pc02_prefix}/lib/libexreader-posix-c02-admission.a;${_pc02_prefix}/lib/libexreader-migration-coordinator-hardening.a;EXReader::exr_library;EXReader::exr_core")
endif()
unset(_pc02_prefix)
