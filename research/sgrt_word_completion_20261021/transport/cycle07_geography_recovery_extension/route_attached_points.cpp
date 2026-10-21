#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <fstream>
#include <functional>
#include <iostream>
#include <queue>
#include <string>
#include <vector>
#include <chrono>
#include <stdexcept>
using namespace std;
template<class T> vector<T> rd(string p){ifstream f(p,ios::binary|ios::ate);if(!f)throw runtime_error(p);auto n=f.tellg();f.seekg(0);vector<T>x((size_t)n/sizeof(T));f.read((char*)x.data(),n);return x;}
struct Out{uint32_t query;uint32_t point;float minutes;};
int main(int argc,char**argv){
 if(argc<3)return 2;string d=argv[1],mode=argv[2];auto ptr=rd<uint64_t>(d+"/rev_indptr.bin");auto to=rd<uint32_t>(d+"/rev_indices.bin");auto w=rd<float>(d+"/rev_weights.bin");uint32_t N=ptr.size()-1;
 if(mode=="forward"){
  vector<uint64_t>p(N+1,0);for(auto v:to)p[v+1]++;for(uint32_t i=0;i<N;i++)p[i+1]+=p[i];auto next=p;vector<uint32_t>t(to.size());vector<float>v(w.size());
  for(uint32_t u=0;u<N;u++)for(uint64_t j=ptr[u];j<ptr[u+1];j++){auto k=next[to[j]]++;t[k]=u;v[k]=w[j];}ptr.swap(p);to.swap(t);w.swap(v);
 }else if(mode!="reverse")throw runtime_error("mode");
 auto qp=rd<uint64_t>(d+"/query_seed_offsets.bin");auto qn=rd<uint32_t>(d+"/query_seed_nodes.bin");auto qc=rd<double>(d+"/query_seed_minutes.bin");auto qconn=rd<double>(d+"/query_connectors.bin");auto qb=rd<double>(d+"/query_budgets.bin");
 auto tn=rd<uint32_t>(d+"/target_seed_nodes.bin");auto ti=rd<uint32_t>(d+"/target_seed_points.bin");auto tc=rd<double>(d+"/target_seed_minutes.bin");auto tconn=rd<double>(d+"/target_connectors.bin");auto tb=rd<double>(d+"/target_budgets.bin");
 vector<int32_t>head(N,-1),link(tn.size(),-1);for(size_t j=0;j<tn.size();j++){link[j]=head[tn[j]];head[tn[j]]=j;}
 vector<double>dist(N),best(tconn.size());vector<uint32_t>epoch(N,0),seen(tconn.size(),0),touched;FILE*out=fopen((d+"/attached_pairs.bin").c_str(),"wb");if(!out)throw runtime_error("output");uint64_t total=0;auto start=chrono::steady_clock::now();
 for(uint32_t q=0;q<qconn.size();q++){
  auto e=q+1;touched.clear();priority_queue<pair<double,uint32_t>,vector<pair<double,uint32_t>>,greater<pair<double,uint32_t>>>heap;
  for(auto j=qp[q];j<qp[q+1];j++){auto u=qn[j];double v=qc[j];if(epoch[u]!=e || v<dist[u]){dist[u]=v;epoch[u]=e;heap.emplace(v,u);}}
  while(!heap.empty()){
   auto [du,u]=heap.top();heap.pop();if(epoch[u]!=e || du!=dist[u])continue;if(du+qconn[q]>qb[q])break;
   for(int32_t j=head[u];j>=0;j=link[j]){auto t=ti[j];double v=du+tc[j];if(v+qconn[q]+tconn[t]<=min(qb[q],tb[t])){if(seen[t]!=e){seen[t]=e;best[t]=v;touched.push_back(t);}else if(v<best[t])best[t]=v;}}
   for(uint64_t j=ptr[u];j<ptr[u+1];j++){auto v=to[j];double nd=du+(double)w[j];if(nd+qconn[q]<=qb[q] && (epoch[v]!=e || nd<dist[v])){epoch[v]=e;dist[v]=nd;heap.emplace(nd,v);}}
  }
  sort(touched.begin(),touched.end());for(auto t:touched){Out row{q,t,(float)best[t]};fwrite(&row,sizeof(row),1,out);total++;}
  if(q%10==0||q+1==qconn.size()){fflush(out);cerr<<"queries "<<q+1<<"/"<<qconn.size()<<" pairs "<<total<<" seconds "<<chrono::duration<double>(chrono::steady_clock::now()-start).count()<<"\n";}
 }
 fclose(out);return 0;
}
