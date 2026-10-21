"""Build positive historical regional context only after guardian review is recorded."""
from pathlib import Path
import pandas as pd,json,hashlib,datetime
H=Path(__file__).resolve().parent;ROOT=H.parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 admission=json.loads((H/'guardian_source_admission.json').read_text());assert admission['finite_29_mapping_accepted'] is True
 protocol=json.loads((H/'preregistration.json').read_text());mapping=json.loads((H/'finite_source29_to_axis_regions.json').read_text());assert sha(H/'finite_source29_to_axis_regions.json')==protocol['map_sha256']
 axis_path=ROOT/'data/source_controls_cycle05/full_settlement_axis_cycle05_federal_children.parquet';axis=pd.read_parquet(axis_path);assert len(axis)==173862 and axis.id.is_unique
 indexed={r['axis_region_key']:r for r in mapping};assert len(indexed)==29
 if admission.get('NAO_primary_hierarchy_accepted'):
  indexed['ненецкий']=dict(source_unit='Архангельская область, в том числе Ненецкий национальный округ',source_pdf_page_1based=2,source_printed_page=6)
 out=axis[['id','region']].copy();native=axis.source_record_id_2021.notna()&~axis.axis_kind.eq('federal_territory_source_unit');match=axis.region.isin(indexed)&native
 out['nonchernozem_historical_regional_context_1974']=pd.array([True if v else pd.NA for v in match],dtype='boolean')
 out['nonchernozem_context_scope']='inherited_historical_region_context_presence_only'
 out['nonchernozem_context_year']=1974;out['nonchernozem_source_publication_year']=1975
 out['source_unit_1974']=axis.region.map({k:v['source_unit'] for k,v in indexed.items()}).where(match)
 out['source_definition_printed_page']=pd.array([209 if b else pd.NA for b in match],dtype='Int64')
 out['own_2021_source_record']=axis.source_record_id_2021.where(native)
 out['context_status']='unknown_outside_finite_positive_context'
 out.loc[~native,'context_status']='unknown_no_own_2021_NP_observation'
 out.loc[axis.region.isin(['москва','санкт петербург','севастополь']),'context_status']='unknown_federal_city_historical_scope'
 out.loc[axis.region.eq('крым'),'context_status']='unknown_outside_1974_RSFSR_scope'
 out.loc[match,'context_status']='positive_historical_regional_inheritance_boundaries_not_proven'
 out['unchanged_1974_to_2021_boundary_proven']=False
 out['own_soil_or_parcel_membership_proven']=False
 out['sufficient_Word_type7_evidence']=False
 out.to_parquet(H/'settlement_historical_nonchernozem_context_1974.parquet',index=False)
 out.groupby(['region','context_status'],observed=True,dropna=False).size().rename('rows').reset_index().to_csv(H/'region_context_accounting.csv',index=False)
 pd.DataFrame(mapping).to_csv(H/'primary_29_units.csv',index=False)
 checks=dict(axis_rows=len(axis),axis_ids_unique=True,axis_order_preserved=out.id.equals(axis.id),positive_rows=int(match.sum()),unknown_rows=int((~match).sum()),false_rows=int(out.nonchernozem_historical_regional_context_1974.eq(False).sum()),positive_region_keys=sorted(out.loc[match,'region'].unique().tolist()),no_historical_only_positive=bool((~match|native).all()),federal_city_positive_rows=int(match[axis.region.isin(['москва','санкт петербург','севастополь'])].sum()),model_or_typology_input_modified=False)
 assert checks['false_rows']==0 and checks['federal_city_positive_rows']==0
 receipt=dict(status='ACTUAL_PRIMARY_SOURCE_DERIVED_CONTEXT',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),axis_path=str(axis_path.relative_to(ROOT)),axis_sha256=sha(axis_path),protocol_sha256=sha(H/'preregistration.json'),mapping_sha256=sha(H/'finite_source29_to_axis_regions.json'),admission_sha256=sha(H/'guardian_source_admission.json'),source_pdfs=[dict(file=str(p.relative_to(H)),sha256=sha(p)) for p in sorted((H/'sources').glob('*.pdf'))],output_sha256=sha(H/'settlement_historical_nonchernozem_context_1974.parquet'),checks=checks,interpretation=protocol['value_semantics'],scientific_type7_acceptance=False)
 (H/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(checks,ensure_ascii=False))
if __name__=='__main__':main()
