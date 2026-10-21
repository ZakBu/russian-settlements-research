#include <cstdint>
#include <cstring>
extern "C" int match(const int64_t *row,const int32_t *col,const float *v,int64_t n,const int64_t *ip,const int32_t *ix,const float *data,uint8_t *seen,int64_t *bad){
 for(int64_t k=0;k<n;k++){
  int64_t lo=ip[row[k]],hi=ip[row[k]+1];
  while(lo<hi){auto m=(lo+hi)/2;if(ix[m]<col[k])lo=m+1;else hi=m;}
  if(lo>=ip[row[k]+1]||ix[lo]!=col[k]){*bad=k;return 1;}
  if(std::memcmp(&v[k],&data[lo],sizeof(float))){*bad=k;return 2;}
  if(seen[lo]){*bad=k;return 3;}seen[lo]=1;
 }
 return 0;
}
