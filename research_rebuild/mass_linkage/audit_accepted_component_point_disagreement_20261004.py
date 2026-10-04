"""Diagnose exact interyear point disagreement; does not mutate admissions."""
from pathlib import Path
import json,hashlib,duckdb
REPO=Path(__file__).resolve().parents[2]
CORE=Path('/workspace/settlements-work/continuation_20261004/R4/final_long_preparation/fifth_canonical_long_v2/source_preserving_core.parquet')
OUT=Path('/workspace/settlements-work/continuation_20261004/root/fifth_point_disagreement_audit_v2')
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 cfgpath=REPO/'config/mass_joint_20261004.json'; cfg=json.loads(cfgpath.read_text())
 manifest=json.loads(CORE.with_suffix('.manifest.json').read_text())
 for name,key in [('identity','working_identity_graph'),('coordinates','working_point_uses')]:
  assert manifest['inputs'][name]['sha256']==cfg[key+'_sha256']==sha(cfg[key])
 assert manifest['outputs']['parquet']['sha256']==sha(CORE)
 con=duckdb.connect(config={'threads':1,'memory_limit':'1GB'})
 con.read_parquet(str(CORE)).create_view('core')
 con.execute("create view points as select entity_id,source_record_id,observation_year,latitude,longitude from core where record_type='census' and latitude is not null and longitude is not null")
 con.execute("""create view pair_distances as select a.entity_id,a.source_record_id left_source_record_id,b.source_record_id right_source_record_id,
 12742.0176*asin(sqrt(least(1.0,pow(sin(radians(a.latitude-b.latitude)/2),2)+cos(radians(a.latitude))*cos(radians(b.latitude))*pow(sin(radians(a.longitude-b.longitude)/2),2)))) distance_km
 from points a join points b on a.entity_id=b.entity_id and a.source_record_id<b.source_record_id""")
 con.execute("create view conflicts as select entity_id,max(distance_km) max_point_distance_km,count(*) filter(where distance_km>5) disagreeing_pairs from pair_distances group by entity_id having max(distance_km)>5")
 OUT.mkdir(parents=True,exist_ok=False)
 pairs=OUT/'disagreeing_point_pairs.parquet'; records=OUT/'affected_census_point_records.parquet'
 con.execute('copy (select * from pair_distances where distance_km>5) to ? (format parquet,compression zstd)',[str(pairs)])
 con.execute('copy (select c.*,d.max_point_distance_km from core c join conflicts d using(entity_id) where c.record_type=\'census\') to ? (format parquet,compression zstd)',[str(records)])
 metrics=con.execute("select observation_year as census_year,count(*) affected_source_rows,sum(population_value) affected_recorded_population,count(*) filter(where census_full_chain and latitude is not null) affected_joint_rows,sum(population_value) filter(where census_full_chain and latitude is not null) affected_joint_population from core join conflicts using(entity_id) where record_type='census' group by all order by census_year").fetchdf().to_dict('records')
 coverage=json.loads(Path(cfg['working_coverage']).read_text())
 # This diagnostic never labels identities false, and >5km alone can be a
 # valid large/polycentric city. It quantifies a stricter screen, not truth.
 for m in metrics:
  y=int(m['census_year']); axis=next(r for r in coverage['census_metrics'] if r['year']==y)
  joint=axis['axes']['joint_admitted_coordinate_and_full_chain']['known_population']
  m['joint_NP_population_without_point_disagreement']=joint-int(m['affected_joint_population'] or 0)
  m['joint_NP_fraction_without_point_disagreement']=m['joint_NP_population_without_point_disagreement']/cfg['official_controls'][str(y)]
 receipt={'status':'diagnostic_only_exact_point_disagreement_no_admission_changes','threshold_km':5,'exact_haversine':True,
 'disagreeing_components':con.execute('select count(*) from conflicts').fetchone()[0],
 'over_20km_components':con.execute('select count(*) from conflicts where max_point_distance_km>20').fetchone()[0],
 'metrics':metrics,'config_sha256':sha(cfgpath),'core_sha256':sha(CORE),'script_sha256':sha(__file__),
 'outputs':{str(p):sha(p) for p in [pairs,records]},
 'limitations':['Distance threshold is a contradiction screen, not automatic evidence of wrong identity or point; large/polycentric settlements need scope review.','Named and coded raw GeoKLADR 2011 records may still carry erroneous coordinates; raw row provenance alone does not establish coordinate correctness.','Existing immutable admission ledgers retained; dispute decisions and source-specific corrections require reviewed witnesses.']}
 (OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(receipt,ensure_ascii=False))
if __name__=='__main__':main()
