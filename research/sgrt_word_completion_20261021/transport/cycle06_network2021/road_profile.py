"""Static public-car profile; historical source tags, explicit scenario speeds."""
import json,re
import numpy as np
SPEED={'motorway':100,'motorway_link':50,'trunk':90,'trunk_link':50,'primary':70,'primary_link':40,'secondary':60,'secondary_link':35,'tertiary':50,'tertiary_link':30,'unclassified':40,'residential':30,'living_street':15,'service':20,'track':15,'road':25}
DENY={'no','private','agricultural','forestry','delivery','customers','permit','official','psv','bus','taxi','emergency'}
def effective_access(t):return next((t[k] for k in ('motorcar','motor_vehicle','vehicle','access') if k in t),'')
def exclusions(t):
 reasons=[]
 if effective_access(t) in DENY:reasons.append('effective_car_access_'+effective_access(t))
 for k in ['winter_road','ice_road']:
  if t.get(k,'').strip().lower() in {'yes','1','true'}:reasons.append(k)
 if t.get('seasonal','').strip().lower() not in {'','no','0','false'}:reasons.append('seasonal')
 for k in ['access:conditional','motor_vehicle:conditional','motorcar:conditional']:
  if t.get(k,'').strip():reasons.append(k)
 # Reversible/alternating/conditional direction cannot become unrestricted bidirectional arcs.
 for k in ['oneway:conditional','oneway:motor_vehicle:conditional','oneway:motorcar:conditional']:
  if t.get(k,'').strip():reasons.append(k)
 direction=next((t[k].strip().lower() for k in ('oneway:motorcar','oneway:motor_vehicle','oneway') if k in t),'')
 if direction not in {'','yes','true','1','no','false','0','-1'}:reasons.append('unsupported_oneway_'+direction)
 return reasons

def oneway(t):
 value=next((t[k].strip().lower() for k in ('oneway:motorcar','oneway:motor_vehicle','oneway') if k in t),'')
 if value in {'no','false','0'}:return 0
 if value=='-1':return -1
 if value in {'yes','true','1'}:return 1
 return 1 if t.get('junction')=='roundabout' or t.get('highway') in {'motorway','motorway_link'} else 0

def speed(t):
 base=SPEED[t['highway']];v=t.get('maxspeed','');m=re.match(r'^\s*(\d+(?:\.\d+)?)',v)
 if m:base=min(float(m.group(1))*(1.60934 if 'mph' in v else 1),130)
 factor=.65 if t.get('surface') in {'unpaved','ground','dirt','earth','mud','sand','grass'} else .8 if t.get('surface') in {'gravel','fine_gravel','compacted','pebblestone'} else 1
 return max(5,base*factor)
def xyz(lat,lon):
 a,b=np.radians(lat),np.radians(lon);return np.column_stack([np.cos(a)*np.cos(b),np.cos(a)*np.sin(b),np.sin(a)])
def distances(lat,lon):
 a,b=np.radians(lat),np.radians(lon);v=np.sin(np.diff(a)/2)**2+np.cos(a[:-1])*np.cos(a[1:])*np.sin(np.diff(b)/2)**2
 return 6371.0088*2*np.arcsin(np.sqrt(np.clip(v,0,1)))
