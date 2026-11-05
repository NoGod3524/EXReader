/* SPDX-License-Identifier: MIT */
#ifndef PC02_IO_H
#define PC02_IO_H
#include <exr_pc02.h>
typedef struct {unsigned char identity[16],size[8];char sha[65];} pc02_file;
int pc02io_same(const pc02_identity *,const pc02_identity *);
void pc02io_put64(unsigned char *,uint64_t);
uint64_t pc02io_get64(const unsigned char *);
void pc02io_putid(unsigned char *,const pc02_identity *);
pc02_identity pc02io_getid(const unsigned char *);
int pc02io_identity(int fd,int directory,int private_mode,pc02_identity *);
int pc02io_hash(int fd,pc02_file *);
int pc02io_equal(const pc02_file *,const pc02_file *);
int pc02io_match(int parent,const char *leaf,const pc02_file *);
int pc02io_absent(int parent,const char *leaf);
int pc02io_quiet(int parent,const char *leaf);
int pc02io_copy(int source,int destination,const pc02_file *expected);
int pc02io_leaf(const char *);
#endif
