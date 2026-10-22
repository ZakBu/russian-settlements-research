import pandas as pd
from build_registry import relation,choose,signature

def part(labels):return pd.DataFrame({'id':list('abcd'),'unit_id':labels})
def main():
 p0=part(['a','b','c','d']);p1=part(['x','x','y','y']);p2=part(['q','q','q','q']);same=part(['P','P','Q','Q']);cross=part(['1','2','1','2'])
 assert relation(p0,p1)[:2]==(True,False)
 assert relation(p1,same)[:2]==(True,True)
 assert relation(p1,cross)[:2]==(False,False)
 stable=pd.DataFrame({'candidate_cap':[30,45,60,90,120],'accepted':[False,True,True,True,True]}).set_index('candidate_cap')
 kept,d=choose({30:p0,45:p1,60:same,90:cross,120:p2},stable)
 assert kept==[45,120] and [x['empirical_level']for x in d if x['promoted']]==[0,1]
 assert d[2]['reason']=='equivalent_partition_earliest_eligible_cut_retained' and d[3]['reason']=='not_exact_whole_child_coarsening'
 stable.accepted=False;assert choose({30:p0,45:p1},stable)[0]==[]
 stable.accepted=True;assert choose({30:p0,45:p1},stable)[0]==[30,45]
 for bad in [p1.iloc[:3],pd.concat([p1,p1.iloc[:1]],ignore_index=True)]:
  try:relation(p0,bad)
  except ValueError:pass
  else:raise AssertionError('missing/duplicate atoms not rejected')
 assert signature(['a','b'])==signature(['b','a']) and signature(['a','b'])!=signature(['ab'])
 print('Registry no forcedcount/stability gate/equivalent-label dedup/non-nested exclusion/axis+duplicate guards/signatures/0-up numbering PASS')
if __name__=='__main__':main()
