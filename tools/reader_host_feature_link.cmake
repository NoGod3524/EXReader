# SPDX-License-Identifier: MIT
# Narrow host-feature link closure for the five reviewed optional packages.
#
# This module does not build, wrap, relabel or copy any module or SDK target.
# It reads the real installed graph (imported targets, their origins and the
# existing installed-SDK provenance guard), refuses graphs that would put a
# second SDK implementation or a second product store provider into one
# process, and then links the caller's own final artifact to the unchanged
# targets. Shared SDK use is expressed as EXReader::exreader (the installed
# shared library), never by re-tagging EXReader::exr_* static archives.
#
# Canonical module set (exactly these, no more, no less):
#   annotations -> EXReaderAnnotationImport::reader_annotation_import
#                  EXReaderAnnotationExport::reader_annotation_export
#   font        -> EXReaderFontLibrary::reader_font_library
#   original    -> EXReaderOriginalExport::reader_original_export
#   history     -> EXReaderJumpHistory::reader_jump_history
#   sync        -> EXReaderSyncView::reader_sync_view
#
# Usage in a host project (see docs/reader-wave3-s19/README.md):
#   find_package(EXReader <ver> EXACT CONFIG REQUIRED COMPONENTS core library)
#   find_package(EXReaderProductCatalog 0.1.0 EXACT CONFIG REQUIRED)
#   find_package(EXReaderAnnotationImport 0.1.0 EXACT CONFIG REQUIRED)
#   find_package(EXReaderAnnotationExport 0.1.0 EXACT CONFIG REQUIRED)
#   find_package(EXReaderFontLibrary 0.1.0 EXACT CONFIG REQUIRED)
#   find_package(EXReaderOriginalExport 0.1.0 EXACT CONFIG REQUIRED)
#   find_package(EXReaderJumpHistory 0.1.0 EXACT CONFIG REQUIRED)
#   find_package(EXReaderSyncView 0.1.0 EXACT CONFIG REQUIRED)
#   find_package(EXReaderHostFeatureLink 1.0.0 EXACT CONFIG REQUIRED)
#   exr_reader_host_feature_link_declare(host_features
#     SDK_PREFIX <installed sdk> SDK_VERSION <exact> SDK_LINK shared
#     STORE_PREFIX <installed catalog> PACKAGE_PREFIXES <installed module prefix>...)
#   add_library(product_features SHARED features.cpp)
#   exr_reader_host_feature_link_attach(product_features host_features
#     ROLE FEATURE_DSO)
#   add_executable(product HOST.cpp)
#   exr_reader_host_feature_link_attach(product host_features
#     ROLE HOST_EXECUTABLE HOST_OF product_features)

if(DEFINED EXR_READER_HOST_FEATURE_LINK_INCLUDED)
  return()
endif()
set(EXR_READER_HOST_FEATURE_LINK_INCLUDED 1)

set(EXR_HOST_FEATURE_LINK_VERSION "1.0.0")
set(EXR_HOST_FEATURE_MODULES annotations font original history sync)
set(_exr_hfl_packages
  "annotations;EXReaderAnnotationImport;0.1.0;EXReaderAnnotationImport::reader_annotation_import"
  "annotations;EXReaderAnnotationExport;0.1.0;EXReaderAnnotationExport::reader_annotation_export"
  "font;EXReaderFontLibrary;0.1.0;EXReaderFontLibrary::reader_font_library"
  "original;EXReaderOriginalExport;0.1.0;EXReaderOriginalExport::reader_original_export"
  "history;EXReaderJumpHistory;0.1.0;EXReaderJumpHistory::reader_jump_history"
  "sync;EXReaderSyncView;0.1.0;EXReaderSyncView::reader_sync_view")

function(_exr_hfl_fail message)
  message(FATAL_ERROR "EXReaderHostFeatureLink: ${message}")
endfunction()

function(_exr_hfl_realpath out path)
  if(NOT EXISTS "${path}")
    _exr_hfl_fail("path does not exist: ${path}")
  endif()
  file(REAL_PATH "${path}" _resolved)
  set(${out} "${_resolved}" PARENT_SCOPE)
endfunction()

# A package directory must live inside one declared install prefix.
function(_exr_hfl_require_inside label directory prefixes)
  _exr_hfl_realpath(_directory "${directory}")
  foreach(_prefix IN LISTS prefixes)
    _exr_hfl_realpath(_root "${_prefix}")
    cmake_path(IS_PREFIX _root "${_directory}" NORMALIZE _inside)
    if(_inside)
      return()
    endif()
  endforeach()
  _exr_hfl_fail("${label} was resolved outside every declared install prefix: ${_directory}")
endfunction()

function(_exr_hfl_require_no_source_provider)
  # A source build of the product store (add_subdirectory(store/native)) beside
  # the installed provider would give one process two catalog providers. Only
  # the imported package targets are allowed.
  foreach(_name reader_catalog reader_catalog_sqlite reader_catalog_sdk)
    if(TARGET ${_name})
      get_target_property(_imported ${_name} IMPORTED)
      if(NOT _imported)
        _exr_hfl_fail("a private product store build is present (${_name}); consume the installed EXReaderProductCatalog instead")
      endif()
    endif()
  endforeach()
endfunction()

function(exr_reader_host_feature_link_declare target)
  cmake_parse_arguments(ARG "" "SDK_PREFIX;SDK_VERSION;STORE_PREFIX;SDK_LINK"
    "PACKAGE_PREFIXES;MODULES" ${ARGN})
  if(NOT ARG_SDK_PREFIX OR NOT ARG_SDK_VERSION OR NOT ARG_STORE_PREFIX OR NOT ARG_SDK_LINK)
    _exr_hfl_fail("declare(${target}) needs SDK_PREFIX, SDK_VERSION, STORE_PREFIX and SDK_LINK")
  endif()
  if(NOT ARG_PACKAGE_PREFIXES)
    _exr_hfl_fail("declare(${target}) needs at least one PACKAGE_PREFIXES entry")
  endif()
  if(TARGET ${target})
    _exr_hfl_fail("closure target already exists: ${target}")
  endif()
  set(_modules ${ARG_MODULES})
  if(NOT _modules)
    set(_modules ${EXR_HOST_FEATURE_MODULES})
  endif()
  list(SORT _modules)
  set(_expected ${EXR_HOST_FEATURE_MODULES})
  list(SORT _expected)
  if(NOT _modules STREQUAL _expected)
    _exr_hfl_fail("the closure must name exactly the five reviewed modules (${_expected}), got (${_modules})")
  endif()

  if(NOT ARG_SDK_LINK MATCHES "^(shared|static)$")
    _exr_hfl_fail("SDK_LINK must be shared or static: ${ARG_SDK_LINK}")
  endif()
  if(NOT ARG_SDK_VERSION MATCHES "^3\.(40|41)\.0$")
    _exr_hfl_fail("unsupported exact SDK version: ${ARG_SDK_VERSION}")
  endif()

  # One SDK, one product store, one module origin.
  _exr_hfl_require_inside("the imported SDK" "${EXReader_DIR}" "${ARG_SDK_PREFIX}")
  if(NOT "${EXReader_VERSION}" STREQUAL "${ARG_SDK_VERSION}")
    _exr_hfl_fail("configured SDK is ${EXReader_VERSION}, the host declares ${ARG_SDK_VERSION}")
  endif()
  _exr_hfl_require_inside("the imported product catalog" "${EXReaderProductCatalog_DIR}" "${ARG_STORE_PREFIX}")
  _exr_hfl_require_no_source_provider()

  set(_link_targets)
  foreach(_entry IN LISTS _exr_hfl_packages)
    list(GET _entry 0 _module)
    list(GET _entry 1 _package)
    list(GET _entry 2 _version)
    list(GET _entry 3 _link)
    if(NOT TARGET "${_link}")
      _exr_hfl_fail("module ${_module} is not imported; find_package(${_package} ${_version} EXACT CONFIG REQUIRED) first")
    endif()
    if(NOT "${${_package}_VERSION}" STREQUAL "${_version}")
      _exr_hfl_fail("${_package} must be the installed ${_version}, got ${${_package}_VERSION}")
    endif()
    _exr_hfl_require_inside("${_package}" "${${_package}_DIR}" "${ARG_PACKAGE_PREFIXES}")
    list(APPEND _link_targets "${_link}")
  endforeach()

  if(ARG_SDK_LINK STREQUAL "shared")
    if(NOT TARGET EXReader::exreader)
      _exr_hfl_fail("the installed SDK does not export EXReader::exreader; a shared closure needs the shared SDK library")
    endif()
    get_target_property(_exreader_type EXReader::exreader TYPE)
    if(NOT _exreader_type STREQUAL "SHARED_LIBRARY")
      _exr_hfl_fail("EXReader::exreader is not a shared library: ${_exreader_type}")
    endif()
    set(_sdk_target EXReader::exreader)
  else()
    if(NOT TARGET EXReader::exr_core)
      _exr_hfl_fail("the installed SDK does not export EXReader::exr_core")
    endif()
    set(_sdk_target EXReader::exr_core)
  endif()

  # Reuse the installed provenance guard the optional packages already ship:
  # it authenticates header and archive origins of the whole SDK closure and
  # refuses a relabelled or foreign EXReader:: target.
  if(NOT COMMAND _exr_sdk_target_provenance)
    _exr_hfl_fail("the installed SDK provenance guard is missing; import an optional package before declaring the closure")
  endif()
  _exr_sdk_target_provenance("${_sdk_target}" "${EXReader_DIR}" "${ARG_SDK_VERSION}")

  add_library(${target} INTERFACE)
  # The single SDK provider comes first on the link line. Module archives that
  # follow resolve their public SDK symbols from it instead of contributing a
  # second copy of the SDK objects to a product DSO.
  target_link_libraries(${target} INTERFACE "${_sdk_target}")
  foreach(_link IN LISTS _link_targets)
    target_link_libraries(${target} INTERFACE "${_link}")
  endforeach()
  target_link_libraries(${target} INTERFACE EXReaderProductCatalog::reader_catalog)
  target_link_libraries(${target} INTERFACE EXReaderProductCatalog::reader_catalog_sqlite)
  set_target_properties(${target} PROPERTIES
    EXR_HOST_FEATURE_SDK_MODE "${ARG_SDK_LINK}"
    EXR_HOST_FEATURE_SDK_TARGET "${_sdk_target}"
    EXR_HOST_FEATURE_SDK_VERSION "${ARG_SDK_VERSION}"
    EXR_HOST_FEATURE_STORE_TARGETS "EXReaderProductCatalog::reader_catalog;EXReaderProductCatalog::reader_catalog_sqlite"
    EXR_HOST_FEATURE_MODULE_TARGETS "${_link_targets}")
  set(EXReaderHostFeatureLink_${target}_SDK_MODE "${ARG_SDK_LINK}" PARENT_SCOPE)
endfunction()

function(_exr_hfl_rpath target role)
  # Normal platform rpath strategy: the installed SDK and the feature library
  # are found next to the artifact instead of through a build tree.
  if(APPLE)
    if(role STREQUAL "FEATURE_DSO")
      set_property(TARGET ${target} APPEND PROPERTY INSTALL_RPATH "@loader_path")
    else()
      set_property(TARGET ${target} APPEND PROPERTY INSTALL_RPATH "@loader_path;@loader_path/../lib")
    endif()
  elseif(UNIX)
    if(role STREQUAL "FEATURE_DSO")
      set_property(TARGET ${target} APPEND PROPERTY INSTALL_RPATH "$ORIGIN")
    else()
      set_property(TARGET ${target} APPEND PROPERTY INSTALL_RPATH "$ORIGIN;$ORIGIN/../lib")
    endif()
  endif()
endfunction()

function(exr_reader_host_feature_link_attach target closure)
  cmake_parse_arguments(ARG "" "ROLE;HOST_OF" "" ${ARGN})
  if(NOT TARGET ${target} OR NOT TARGET ${closure})
    _exr_hfl_fail("attach(${target}) needs an existing artifact target and a declared closure")
  endif()
  get_target_property(_sdk_mode ${closure} EXR_HOST_FEATURE_SDK_MODE)
  get_target_property(_sdk_target ${closure} EXR_HOST_FEATURE_SDK_TARGET)
  get_target_property(_modules ${closure} EXR_HOST_FEATURE_MODULE_TARGETS)
  get_target_property(_type ${target} TYPE)
  set(_role "${ARG_ROLE}")

  if(_role STREQUAL "FEATURE_DSO")
    if(NOT _type MATCHES "SHARED_LIBRARY|MODULE_LIBRARY")
      _exr_hfl_fail("${target} must be a shared library for the FEATURE_DSO role, got ${_type}")
    endif()
    if(NOT _sdk_mode STREQUAL "shared")
      _exr_hfl_fail("${target} is a product DSO but the closure links the static SDK; a product DSO must not embed a second SDK implementation")
    endif()
    get_property(_owner GLOBAL PROPERTY EXR_HFL_FEATURE_DSO)
    if(_owner)
      _exr_hfl_fail("only one FEATURE_DSO may own the five modules in one process: ${_owner} already does")
    endif()
    set_property(GLOBAL PROPERTY EXR_HFL_FEATURE_DSO "${target}")
    set_property(GLOBAL PROPERTY EXR_HFL_STORE_PROVIDER "${target}")
    target_link_libraries(${target} PRIVATE ${closure})
    _exr_hfl_rpath(${target} "${_role}")
    file(WRITE "${CMAKE_BINARY_DIR}/exr-host-feature-link-${target}.txt"
      "target=${target}\nrole=${_role}\nclosure=${closure}\nsdk=${_sdk_target}\nmodules=${_modules}\nstore_provider=${target}\n")
  elseif(_role STREQUAL "HOST_EXECUTABLE")
    if(NOT _type STREQUAL "EXECUTABLE")
      _exr_hfl_fail("${target} must be an executable for the HOST_EXECUTABLE role, got ${_type}")
    endif()
    if(NOT ARG_HOST_OF)
      _exr_hfl_fail("HOST_EXECUTABLE needs HOST_OF <feature dso target>")
    endif()
    if(NOT TARGET ${ARG_HOST_OF})
      _exr_hfl_fail("HOST_OF target does not exist: ${ARG_HOST_OF}")
    endif()
    get_property(_owner GLOBAL PROPERTY EXR_HFL_FEATURE_DSO)
    if(NOT _owner STREQUAL "${ARG_HOST_OF}")
      _exr_hfl_fail("${ARG_HOST_OF} is not the declared feature owner; declare it with ROLE FEATURE_DSO first")
    endif()
    get_property(_store GLOBAL PROPERTY EXR_HFL_STORE_PROVIDER)
    if(NOT _store STREQUAL "${ARG_HOST_OF}")
      _exr_hfl_fail("the product store provider is ${_store}, the host claims ${ARG_HOST_OF}")
    endif()
    if(NOT _sdk_mode STREQUAL "shared")
      _exr_hfl_fail("a host that loads the feature DSO must use the shared SDK, not a second static copy")
    endif()
    # The host process must own exactly one SDK and no module/store copy: the
    # feature DSO is the only owner of the five modules and the catalog.
    get_target_property(_own_links ${target} LINK_LIBRARIES)
    if(NOT _own_links)
      set(_own_links)
    endif()
    foreach(_link IN LISTS _modules)
      if(_link IN_LIST _own_links)
        _exr_hfl_fail("the host executable links module ${_link}; the feature DSO must be its only copy")
      endif()
    endforeach()
    foreach(_store_target EXReaderProductCatalog::reader_catalog EXReaderProductCatalog::reader_catalog_sqlite)
      if(_store_target IN_LIST _own_links)
        _exr_hfl_fail("the host executable links ${_store_target}; the feature DSO is the only product store provider")
      endif()
    endforeach()
    target_link_libraries(${target} PRIVATE "${_sdk_target}")
    _exr_hfl_rpath(${target} "${_role}")
    file(WRITE "${CMAKE_BINARY_DIR}/exr-host-feature-link-${target}.txt"
      "target=${target}\nrole=${_role}\nhost_of=${ARG_HOST_OF}\nsdk=${_sdk_target}\nmodules=none\nstore_provider=${ARG_HOST_OF}\n")
  elseif(_role STREQUAL "STANDALONE_EXECUTABLE")
    if(NOT _type STREQUAL "EXECUTABLE")
      _exr_hfl_fail("${target} must be an executable for the STANDALONE_EXECUTABLE role, got ${_type}")
    endif()
    get_property(_owner GLOBAL PROPERTY EXR_HFL_FEATURE_DSO)
    if(_owner)
      _exr_hfl_fail("a FEATURE_DSO (${_owner}) already owns the modules; a standalone executable would be a second copy")
    endif()
    set_property(GLOBAL PROPERTY EXR_HFL_STORE_PROVIDER "${target}")
    target_link_libraries(${target} PRIVATE ${closure})
    _exr_hfl_rpath(${target} "${_role}")
    file(WRITE "${CMAKE_BINARY_DIR}/exr-host-feature-link-${target}.txt"
      "target=${target}\nrole=${_role}\nclosure=${closure}\nsdk=${_sdk_target}\nmodules=${_modules}\nstore_provider=${target}\n")
  else()
    _exr_hfl_fail("unknown ROLE '${_role}'; use FEATURE_DSO, HOST_EXECUTABLE or STANDALONE_EXECUTABLE")
  endif()
endfunction()
