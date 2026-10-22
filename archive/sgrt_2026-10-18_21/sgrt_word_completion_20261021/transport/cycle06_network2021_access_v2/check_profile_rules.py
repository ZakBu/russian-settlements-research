"""Check semantically distinct car/access/direction cases before historical routing."""
import json
from pathlib import Path
from road_profile import effective_access,oneway,exclusions,speed
cases=[
 ({'highway':'residential','access':'bus_only'},'effective_car_access_deny_bus_only',0),
 ({'highway':'residential','access':'military'},'effective_car_access_deny_military',0),
 ({'highway':'residential','access':'pedestrian'},'effective_car_access_deny_pedestrian',0),
 ({'highway':'residential','access':'unknown'},'effective_car_access_uncertain_unknown',0),
 ({'highway':'residential','access':' Private '},'effective_car_access_deny_private',0),
 ({'highway':'residential','access':'Всем'},'',0),
 ({'highway':'residential','access':'Да, только летом'},'effective_car_access_deny_да, только летом',0),
 ({'highway':'residential','access':'private','motorcar':''},'empty_high_priority_masks_lower_nonpermit',0),
 ({'highway':'residential','access':'unknown','motorcar':'yes'},'',0),
 ({'highway':'residential','access':'private','motorcar':'yes'},'',0),
 ({'highway':'residential','motor_vehicle':'yes','motorcar':'no'},'effective_car_access_deny_no',0),
 ({'highway':'residential','junction':'roundabout','oneway':'no'},'',0),
 ({'highway':'motorway','oneway':'no'},'',0),
 ({'highway':'primary','oneway':'-1'},'',-1),
 ({'highway':'primary','oneway':'yes','oneway:motorcar':'no'},'',0),
 ({'highway':'track','winter_road':'yes'},'winter_road',0),
 ({'highway':'secondary','oneway':'reversible'},'unsupported_oneway_reversible',0),
 ({'highway':'primary','access:conditional':'no @ (Dec-Mar)'},'access:conditional',0)
]
for tags,reason,direction in cases:
 got=exclusions(tags)
 assert (reason in got) if reason else not got
 if not got:assert oneway(tags)==direction
assert speed({'highway':'residential','maxspeed':'30 mph'})==48.2802
print(json.dumps({'status':'PASS','cases':len(cases),'explicit_mph_speed_conversion':True}))
