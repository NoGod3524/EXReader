#include <stdio.h>
#include <sqlite3.h>
#include <exr/base.h>
#ifdef F07_CODEC
#include <reader_reading_state.h>
#endif
int main(void) {
#ifdef F07_CODEC
 reader_rs_free(NULL);
#endif
 printf("version=%s\n",EXR_VERSION);
 printf("abi=%u\n",(unsigned)EXR_ABI_VERSION);
 printf("sourceid=%s\n",sqlite3_sourceid());
 printf("sqlite_version=%s\n",sqlite3_libversion());
 for(int i=0;sqlite3_compileoption_get(i);++i) printf("option=%s\n",sqlite3_compileoption_get(i));
 return 0;
}
