from pathlib import Path
import pandas as pd,json,hashlib
Z=Path(__file__).parent;B=Z/'batch2_eighteen_literal_part_references';B.mkdir(exist_ok=True)
r=pd.read_csv(Z/'assigned_roster.csv');r=r[r.name_norm.str.contains('часть')];assert len(r)==18
M={'головчино':'Головчино (Белгородская область)','елань колено':'Елань-Колено','троицкое':'Троицкое (Новохопёрский район)','никольское':'Никольское (Аннинский район)','хохол':'Хохол (село)','лозовое':'Лозовое (Воронежская область)','нижний мамон':'Нижний Мамон','архангельское':'Архангельское (Аннинский район)','кущевская':'Кущёвская'}
pages={}
for f in Z.glob('wiki*.json'):
 for p in json.loads(f.read_text()).get('query',{}).get('pages',[]):
  if p.get('coordinates'):pages[p['title']]=(f,p)
sha=lambda f:hashlib.sha256(Path(f).read_bytes()).hexdigest();out=[]
for a in r.itertuples():
 k=a.name_norm.split(' часть')[0];f,p=pages[M[k]];c=p['coordinates'][0]
 out.append(dict(target_source_record_id=a.source_record_id,literal_source_name=a.settlement_name,source_grain='explicit_published_part_of_NP',decision_status='checked_rule_accepted',ownpoint_requirement_disposition='exempt_literal_part_not_whole_NP',whole_NP_reference_name=p['title'],coarse_joint_scope_latitude=c['lat'],coarse_joint_scope_longitude=c['lon'],coordinate_admission_status='coarse_joint_scope_reference_only',own_locality_point=False,part_center_asserted=False,reference_source_file=str(f),reference_source_sha256=sha(f),reference_source_locator=f'page{p["pageid"]}:revision{p["revisions"][0]["revid"]}:coordinates[0]',literal_witness_file=str(Z/'bounded_literal_native_witnesses.csv'),literal_witness_sha256=sha(Z/'bounded_literal_native_witnesses.csv'),rule='Nativepublishedname explicitlylabelsчасть; retainsownrawpartcountandacceptedtemporalroute. WholeNPpointprovidesonlycoarsejointlocation, no fabricatedpartcentre or allocation.',population_values_modified=False,identity_changes=False,temporal_route_changes=False))
pd.DataFrame(out).to_csv(B/'accepted_literal_part_ownpoint_exemptions.csv',index=False)
pins=lambda fs:{str(f):dict(sha256=sha(f),bytes=f.stat().st_size) for f in fs}
(B/'FINAL_manifest.json').write_text(json.dumps(dict(status='FINAL_FROZEN_SOURCE_READY',literal_part_UIDs=18,no_part_center_asserted=True,input_pins=pins([Z/'assigned_roster.csv',Z/'bounded_literal_native_witnesses.csv']+list({Path(x['reference_source_file']) for x in out})),output_pins=pins(list(B.glob('*.csv')))),ensure_ascii=False,indent=2))
print('Frozen18literalpartreferences')
