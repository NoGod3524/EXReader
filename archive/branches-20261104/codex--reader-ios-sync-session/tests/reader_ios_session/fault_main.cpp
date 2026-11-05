/* SPDX-License-Identifier: MIT */
#include <fstream>
#include <string>
#include <thread>
#include <unistd.h>
int ios_fault_session_probe(int,char **);
int main(int argc,char **argv){
  if(argc!=7)return 2;
  {std::ofstream pid(std::string(argv[3])+"/native-pid.json");pid<<"{\"pid\":"<<getpid()<<"}\n";if(!pid)return 2;}
  int result=2;std::thread owner([&]{result=ios_fault_session_probe(argc,argv);});owner.join();return result;
}
