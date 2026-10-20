#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <functional>
#include <iostream>
#include <queue>
#include <string>
#include <vector>
#include <chrono>
#include <filesystem>
using namespace std;
template<class T>vector<T> readfile(string p){ifstream f(p,ios::binary|ios::ate);if(!f)throw runtime_error(p);auto n=f.tellg();f.seekg(0);vector<T> v((size_t)n/sizeof(T));f.read((char*)v.data(),n);return v;}
struct Out {uint32_t origin;uint32_t center;float minutes;};
int main(int argc,char**argv){
 if(argc<2)return 2;string dir=argv[1];auto ptr=readfile<uint64_t>(dir+"/rev_indptr.bin");auto to=readfile<uint32_t>(dir+"/rev_indices.bin");auto w=readfile<float>(dir+"/rev_weights.bin");auto targets=readfile<uint32_t>(dir+"/target_nodes.bin");auto source=readfile<uint32_t>(dir+"/source_nodes.bin");auto budgets=readfile<float>(dir+"/source_budgets.bin");auto connectors=readfile<float>(dir+"/target_connectors.bin");auto sourceconn=readfile<float>(dir+"/source_connectors.bin");
 uint32_t N=ptr.size()-1;vector<int32_t>head(N,-1),next(targets.size(),-1);for(size_t i=0;i<targets.size();i++){next[i]=head[targets[i]];head[targets[i]]=i;}
 vector<float>dist(N);vector<uint32_t>epoch(N,0);uint32_t resume=0;uint64_t committed=0;{ifstream checkpoint(dir+"/route_checkpoint.txt");if(checkpoint)checkpoint>>resume>>committed;}
 if(resume>source.size() || committed%sizeof(Out))throw runtime_error("Invalid checkpoint");
 if(resume){if(!filesystem::exists(dir+"/matrix_pairs.bin") || filesystem::file_size(dir+"/matrix_pairs.bin")<committed)throw runtime_error("Checkpoint exceeds output");filesystem::resize_file(dir+"/matrix_pairs.bin",committed);}
 FILE*out=fopen((dir+"/matrix_pairs.bin").c_str(),resume?"ab":"wb");if(!out)throw runtime_error("Cannot open output");uint64_t output=committed/sizeof(Out);auto start=chrono::steady_clock::now();
 for(uint32_t si=resume;si<source.size();si++){
  uint32_t e=si+1;float budget=budgets[si],conn=sourceconn[si];priority_queue<pair<float,uint32_t>,vector<pair<float,uint32_t>>,greater<pair<float,uint32_t>>>q;dist[source[si]]=0;epoch[source[si]]=e;q.emplace(0,source[si]);uint64_t settled=0;
  while(!q.empty()){
   auto [du,u]=q.top();q.pop();if(epoch[u]!=e || du!=dist[u])continue;if(du+conn>budget)break;settled++;
   for(int32_t t=head[u];t>=0;t=next[t]){if(du+conn+connectors[t]<=budget){Out row{(uint32_t)t,si,du};fwrite(&row,sizeof(row),1,out);output++;}}
   for(uint64_t j=ptr[u];j<ptr[u+1];j++){uint32_t v=to[j];float nd=du+w[j];if(nd+conn<=budget && (epoch[v]!=e || nd<dist[v])){epoch[v]=e;dist[v]=nd;q.emplace(nd,v);}}
  }
  if(si%100==0 || si+1==source.size()){fflush(out);{ofstream checkpoint(dir+"/route_checkpoint.tmp");checkpoint<<si+1<<" "<<output*sizeof(Out)<<"\n";}filesystem::rename(dir+"/route_checkpoint.tmp",dir+"/route_checkpoint.txt");double seconds=chrono::duration<double>(chrono::steady_clock::now()-start).count();cerr<<"centers "<<si+1<<"/"<<source.size()<<" pairs "<<output<<" settledLast "<<settled<<" seconds "<<seconds<<"\n";}
 }
 fclose(out);return 0;
}
