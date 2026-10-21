"""Static public-car profile; historical source tags, explicit scenario speeds."""
import json,re
import numpy as np
SPEED={'motorway':100,'motorway_link':50,'trunk':90,'trunk_link':50,'primary':70,'primary_link':40,'secondary':60,'secondary_link':35,'tertiary':50,'tertiary_link':30,'unclassified':40,'residential':30,'living_street':15,'service':20,'track':15,'road':25}
POLICY=json.loads((__import__('pathlib').Path(__file__).resolve().parent/'finite_access_policy_proposal.json').read_text())
PERMIT=set(POLICY['permit_normalized_literals']);DENY=set(POLICY['deny_normalized_literals']);UNCERTAIN=set(POLICY['uncertain_normalized_literals'])
ACCESS_KEYS=('motorcar','motor_vehicle','vehicle','access')
def effective_access(t):return next((t[k] for k in ACCESS_KEYS if k in t),'')
def access_decision(t):
 raw=effective_access(t);value=raw.strip().casefold()
 category='permit' if value in PERMIT else 'deny' if value in DENY else 'uncertain'
 present=[k for k in ACCESS_KEYS if k in t]
 if present and not value and any(t[k].strip().casefold() not in PERMIT for k in present[1:]):
  return raw,value,'uncertain','empty_high_priority_masks_lower_nonpermit'
 return raw,value,category,'effective_car_access_'+category+'_'+value if category!='permit' else ''
def exclusions(t):
 raw,value,category,reason=access_decision(t)
 return ([reason] if category!='permit' else [])+legacy_other_exclusions(t)
def legacy_other_exclusions(t):
 reasons=[]
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
