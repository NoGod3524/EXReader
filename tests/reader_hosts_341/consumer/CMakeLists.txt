cmake_minimum_required(VERSION 3.24)
project(EXReaderLaterModuleSDK LANGUAGES C CXX)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
endif()
find_package(EXReaderCloudImport 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderThumbnails 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderBookInformation 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderLocalDownloads 0.1.0 EXACT CONFIG REQUIRED)
add_executable(later-sdk consumer.c)
target_link_libraries(later-sdk PRIVATE
  EXReaderCloudImport::reader_cloud_import EXReaderThumbnails::reader_thumbnails
  EXReaderBookInformation::reader_book_information EXReaderLocalDownloads::reader_local_downloads)
