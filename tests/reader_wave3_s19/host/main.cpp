/* SPDX-License-Identifier: MIT */
/* S19 host process: loads the feature DSO at run time, calls the five real
 * modules through it, and reports the process module set plus the SDK identity
 * shared between this executable and the DSO. The executable links the single
 * shared SDK and never links a module or the product store, so the process has
 * exactly one SDK implementation and one product store provider (inside the
 * DSO). */
#include <exreader.h>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>
#if defined(_WIN32)
#include <windows.h>
#include <tlhelp32.h>
#elif defined(__APPLE__)
#include <dlfcn.h>
#include <mach-o/dyld.h>
#else
#include <dlfcn.h>
#include <link.h>
#endif

struct exr_host_features_request {
  const char *work;
  const char *fixtures;
  const char *dav_url;
  const char *dav_auth;
  const char *report;
};

namespace {

struct loaded_module {
  std::string name, path;
};

std::string json_escape(const std::string &value) {
  std::string out = "\"";
  for (unsigned char c : value) {
    if (c == '"' || c == '\\') { out += '\\'; out += (char)c; }
    else if (c < 32) { char buffer[8]; std::snprintf(buffer, sizeof(buffer), "\\u%04x", c); out += buffer; }
    else out += (char)c;
  }
  return out + "\"";
}

std::string base_name(const std::string &path) {
  size_t slash = path.find_last_of("/\\");
  return slash == std::string::npos ? path : path.substr(slash + 1);
}

#if defined(_WIN32)
std::vector<loaded_module> modules_of_process() {
  std::vector<loaded_module> found;
  HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, GetCurrentProcessId());
  if (snapshot == INVALID_HANDLE_VALUE) return found;
  MODULEENTRY32W entry{};
  entry.dwSize = sizeof(entry);
  if (Module32FirstW(snapshot, &entry)) {
    do {
      char narrow[4096] = {0};
      WideCharToMultiByte(CP_UTF8, 0, entry.szModule, -1, narrow, sizeof(narrow) - 1, nullptr, nullptr);
      std::string name = narrow;
      char full[4096] = {0};
      WideCharToMultiByte(CP_UTF8, 0, entry.szExePath, -1, full, sizeof(full) - 1, nullptr, nullptr);
      found.push_back({name, full});
    } while (Module32NextW(snapshot, &entry));
  }
  CloseHandle(snapshot);
  return found;
}
#elif defined(__APPLE__)
std::vector<loaded_module> modules_of_process() {
  std::vector<loaded_module> found;
  uint32_t count = _dyld_image_count();
  for (uint32_t index = 0; index < count; index++) {
    const char *path = _dyld_get_image_name(index);
    if (!path) continue;
    found.push_back({base_name(path), path});
  }
  return found;
}
#else
int collect(struct dl_phdr_info *info, size_t, void *context) {
  std::vector<loaded_module> *found = static_cast<std::vector<loaded_module> *>(context);
  if (info && info->dlpi_name && info->dlpi_name[0]) {
    found->push_back({base_name(info->dlpi_name), info->dlpi_name});
  }
  return 0;
}
std::vector<loaded_module> modules_of_process() {
  std::vector<loaded_module> found;
  dl_iterate_phdr(collect, &found);
  return found;
}
#endif

std::string read_text(const char *path) {
  std::ifstream stream(path, std::ios::binary);
  return std::string((std::istreambuf_iterator<char>(stream)), std::istreambuf_iterator<char>());
}

void *open_library(const char *path) {
#if defined(_WIN32)
  return (void *)LoadLibraryA(path);
#else
  return dlopen(path, RTLD_NOW);
#endif
}

void *lookup(void *library, const char *name) {
#if defined(_WIN32)
  return (void *)GetProcAddress((HMODULE)library, name);
#else
  return dlsym(library, name);
#endif
}

std::string library_error() {
#if defined(_WIN32)
  return "LoadLibrary/GetProcAddress failed: " + std::to_string(GetLastError());
#else
  const char *message = dlerror();
  return message ? std::string(message) : std::string("unknown loader error");
#endif
}

}  // namespace

int main(int argc, char **argv) {
  std::string work, fixtures, dav_url, dso, out;
  const char *authorization = std::getenv("S19_DAV_AUTH");
  std::string dav_auth = authorization ? std::string(authorization) : std::string();
  for (int index = 1; index + 1 < argc; index += 2) {
    std::string key = argv[index], value = argv[index + 1];
    if (key == "--work") work = value;
    else if (key == "--fixtures") fixtures = value;
    else if (key == "--dav-url") dav_url = value;
    else if (key == "--dav-auth-env") {
      const char *from_environment = std::getenv(value.c_str());
      dav_auth = from_environment ? std::string(from_environment) : std::string();
    }
    else if (key == "--dso") dso = value;
    else if (key == "--out") out = value;
    else { std::fprintf(stderr, "unknown argument %s\n", key.c_str()); return 2; }
  }
  if (work.empty() || fixtures.empty() || dav_url.empty() || dso.empty() || out.empty()) {
    std::fprintf(stderr, "usage: --work D --fixtures D --dav-url U [--dav-auth A] --dso P --out F\n");
    return 2;
  }
  void *library = open_library(dso.c_str());
  if (!library) {
    std::fprintf(stderr, "load %s: %s\n", dso.c_str(), library_error().c_str());
    return 3;
  }
  auto run = (int (*)(const struct exr_host_features_request *, char *, size_t))lookup(library, "exr_host_features_run");
  auto version = (const char *(*)(void))lookup(library, "exr_host_features_sdk_version");
  auto pointer = (const void *(*)(void))lookup(library, "exr_host_features_sdk_version_pointer");
  auto count = (int (*)(void))lookup(library, "exr_host_features_module_count");
  if (!run || !version || !pointer || !count) {
    std::fprintf(stderr, "missing entry points in %s\n", dso.c_str());
    return 4;
  }
  std::string report_path = work + "/features-report.json";
  exr_host_features_request request{};
  request.work = work.c_str();
  request.fixtures = fixtures.c_str();
  request.dav_url = dav_url.c_str();
  request.dav_auth = dav_auth.c_str();
  request.report = report_path.c_str();
  char error[1024] = {0};
  int code = run(&request, error, sizeof(error));
  std::vector<loaded_module> modules = modules_of_process();
  std::string report = read_text(report_path.c_str());
  std::string document = "{";
  document += "\"run\":" + std::to_string(code) + ",";
  document += "\"error\":" + json_escape(error) + ",";
  document += "\"dso\":" + json_escape(dso) + ",";
  document += "\"sdk_version\":" + json_escape(exr_version()) + ",";
  document += "\"dso_sdk_version\":" + json_escape(version()) + ",";
  document += "\"exe_pointer\":" + std::to_string((unsigned long long)(uintptr_t)exr_version()) + ",";
  document += "\"dso_pointer\":" + std::to_string((unsigned long long)(uintptr_t)pointer()) + ",";
  document += "\"identity\":" +
              std::to_string((const void *)exr_version() == pointer() &&
                             std::strcmp(version(), exr_version()) == 0 ? 1 : 0) + ",";
  document += "\"modules\":" + std::to_string(count()) + ",";
  document += "\"loaded\":[";
  for (size_t index = 0; index < modules.size(); index++) {
    if (index) document += ",";
    document += "{\"name\":" + json_escape(modules[index].name) + ",\"path\":" +
                json_escape(modules[index].path) + "}";
  }
  document += "],\"report\":" + (report.empty() ? std::string("null") : report) + "}";
  std::ofstream stream(out, std::ios::binary);
  stream.write(document.data(), (std::streamsize)document.size());
  stream.close();
  std::printf("RUN %d\n", code);
  std::printf("IDENTITY %s\n", "see --out");
  return code == 0 ? 0 : 5;
}
