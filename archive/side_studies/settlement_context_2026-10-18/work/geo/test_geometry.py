import json
import numpy as np
from sklearn.neighbors import BallTree
R=6371.0088
# Three distinct UIDs, two colocated; one exactly at sphere distance10km.
xy=np.array([[0.,0.],[0.,0.],[0.,10/R]])
t=BallTree(xy,metric='haversine');js=t.query_radius(xy[:1],r=10/R)[0];neighbors=js[js!=0]
assert set(neighbors)=={1,2},neighbors
# At 10km minus a measurable epsilon boundary point drops.
js=t.query_radius(xy[:1],r=(10-1e-7)/R)[0];assert set(js[js!=0])=={1}
# Longitude wrap-around has2degrees distance, not358degrees.
u=np.deg2rad([[0.,179.],[0.,-179.]])
d=BallTree(u,metric='haversine').query(u,k=2)[0][:,1]*R
assert np.allclose(d,np.deg2rad(2)*R,rtol=1e-12)
print(json.dumps({'status':'pass','checks':['self UID/index only; colocated other retained','closed radius boundary10km','radius boundary epsilon','antimeridian shortest greatcircle'],'sphere_radius_km':R}))
