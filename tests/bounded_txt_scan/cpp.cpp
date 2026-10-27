#include <exreader.h>
#include <type_traits>
using create_fn = exr_status (*)(const exr_source *, exr_font *, const exr_layout_config *, void (*)(void *), exr_pager **, exr_error *);
static_assert(std::is_same<decltype(&exr_txt_pager_create), create_fn>::value, "installed C++ API signature");
int main() { return &exr_txt_pager_create == nullptr; }
