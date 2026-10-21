from pathlib import Path
import numpy as np,json
from prepare_partial_edge_attachments import unit,project,directed_seeds,retained_interval,EARTH
H=Path(__file__).resolve().parent

def main():
 checks=[]
 def check(name,ok):
  checks.append({'name':name,'pass':bool(ok)});assert ok,name
 a,b=unit(np.array([0.,0.]),np.array([0.,2.]));p=unit(1.,1.);d,f,q=project(p,a,b);check('interior_one_degree_perpendicular_known_equatorial_arc',abs(d-EARTH*np.pi/180)<1.e-8 and abs(f-.5)<1.e-10)
 d,f,q=project(unit(0.,-1.),a,b);check('outside_segment_chooses_actual_endpoint',abs(d-EARTH*np.pi/180)<1.e-8 and f==0.)
 d,f,q=project(unit(0.,0.),a,a);check('zero_length_original_segment_no_division',d==0 and f==0 and np.all(q==a))
 d,f,q=project(unit(1.,180.),unit(0.,179.),unit(0.,-179.));check('antimeridian_short_minor_arc',abs(d-EARTH*np.pi/180)<1.e-8 and abs(f-.5)<1.e-10)
 out,inc,k=directed_seeds(10,20,2.,3.,1);check('forward_oneway_interior_partial_direction',out==[{'node':20,'minutes':3.}] and inc==[{'node':10,'minutes':2.}])
 out,inc,k=directed_seeds(10,20,2.,3.,-1);check('reverse_oneway_interior_partial_direction',out==[{'node':10,'minutes':2.}] and inc==[{'node':20,'minutes':3.}])
 out,inc,k=directed_seeds(10,20,2.,3.,0);check('bidirectional_interior_both_endpoints',len(out)==2 and len(inc)==2 and sum(z['minutes'] for z in out)==5.)
 out,inc,k=directed_seeds(10,20,0.,3.,1);check('retained_endpoint_has_zero_cost_graph_access_regardless_selected_way',out==inc==[{'node':10,'minutes':0.}] and k=='left_retained_vertex')
 out,inc,k=directed_seeds(10,20,2.,0.,-1);check('right_retained_endpoint_has_zero_cost_graph_access',out==inc==[{'node':20,'minutes':0.}])
 missing=False
 try:retained_interval(np.array([10,11,12]),np.array([10]),1)
 except ValueError:missing=True
 check('missing_endpoint_dependency_fails_without_nearestjunction_fallback',missing)
 gp,l,r=retained_interval(np.array([10,11,12]),np.array([10,12]),0);check('compressed_interior_uses_actual_two_retained_endpoints',(int(gp[l]),int(gp[r]))==(0,1))
 (H/'synthetic_attachment_checks.json').write_text(json.dumps({'checks':checks,'passed':len(checks),'failed':0},indent=2)+'\n');print('PASS',len(checks))
if __name__=='__main__':main()
