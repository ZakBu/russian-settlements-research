"""Reconcile selected 2010 rows, territorial accounting and working coverage."""
from pathlib import Path
import csv,duckdb,hashlib,json,time
ROOT=Path(__file__).resolve().parents[3]; OUT=Path(__file__).resolve().parent
SOURCE=Path('/workspace/scratch/residual-round2-20261013/final/integrated_spatial_temporal_records.parquet')
FED=ROOT/'publication/stage71/accepted_common_federal_territory_axis.csv'
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 start=time.monotonic();c=duckdb.connect();c.read_parquet(str(SOURCE)).create_view('d');c.read_csv(str(FED),header=True).create_view('f')
 c.execute('create view a as select d.*, working_credit_present or source_record_id in (select population_source_record_id from f where census_year=2010) as accounted from d where census_year=2010')
 def export(q,name):
  cur=c.execute(q);rows=cur.fetchall()
  with (OUT/name).open('w') as fh:
   w=csv.writer(fh);w.writerow([x[0] for x in cur.description]);w.writerows(rows)
  return rows
 sel=c.execute('select sum(population),sum(effective_population),count(*) from a').fetchone()
 fed=c.execute('select sum(territory_population) from f where census_year=2010').fetchone()[0]
 cred=c.execute('select sum(effective_population) from a where working_credit_present').fetchone()[0]+fed
 unc=c.execute('select count(*),sum(effective_population),max(effective_population) from a where not accounted').fetchone()
 cities=export("select source_record_id,settlement_name,region_norm,population,effective_population,accepted_point_present,working_credit_present,accounted,source_file,source_sha256,source_locator from a where type_norm='город' order by effective_population desc",'all_city_records2010.csv')
 assert all(r[7] for r in cities)
 assert int(sel[1]-cred)==int(unc[1]);assert 142856536-int(cred)==int(unc[1])+142856536-int(sel[1])
 export('select region_norm,count(*) as rows,sum(effective_population) as population,max(effective_population) as largest_record from a where not accounted group by region_norm order by population desc','unaccounted_by_region.csv')
 export('select source_record_id,settlement_name,settlement_type,region_norm,district_raw,effective_population,accepted_point_present,source_file,source_sha256,source_locator from a where not accounted order by effective_population desc limit 30','unaccounted_top30.csv')
 summary={'source_rows2010':sel[2],'raw_selected_population2010':int(sel[0]),'effective_selected_population2010':int(sel[1]),'approved_primary_overlay_net_addition':int(sel[1]-sel[0]),'official_control2010':142856536,'control2002':145166731,'official_control_change2002_to2010':142856536-145166731,'working_credited_with_federal_population2010':int(cred),'source_selection_shortfall_vs_control2010':142856536-int(sel[1]),'existing_unaccounted_native_population2010':int(unc[1]),'existing_unaccounted_native_rows2010':unc[0],'largest_existing_unaccounted_native_record2010':int(unc[2]),'total_working_shortfall2010':142856536-int(cred),'city_rows2010':len(cities),'cities_not_accounted2010':sum(not r[7] for r in cities),'million_plus_city_rows':sum(r[4]>=1000000 for r in cities),'input_sha256':{str(SOURCE):sha(SOURCE),str(FED):sha(FED)},'runtime_seconds':round(time.monotonic()-start,3),'limits':'Complete source-city roster comparison is an independent companion audit. Source selection shortfall is a net control residual, not an allocated missing population or evidence of a missing city. This script changes no source/point/link records.'}
 (OUT/'receipt.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
