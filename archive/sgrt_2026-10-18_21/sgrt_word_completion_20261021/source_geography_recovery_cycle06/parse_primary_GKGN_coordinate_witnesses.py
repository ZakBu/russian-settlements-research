from pathlib import Path
import re,json,hashlib,subprocess,pandas as pd,collections,math
H=Path(__file__).resolve().parent

def norm(v):return ' '.join(str(v).casefold().replace('ё','е').replace('–','-').replace('—','-').split())
def main():
 rows=[]
 for region,key in [('Пермский край','perm'),('Московская область','moscow')]:
  pdf=H/'sources'/f'{key}_gkgn_primary_pdf.pdf';txt=subprocess.check_output(['pdftotext','-layout',str(pdf),'-']).decode();(H/'sources'/f'{key}_gkgn_primary_pdf_extracted.txt').write_text(txt);date=re.search(r'населённых пунктов на (\d{2}\.\d{2}\.\d{4})',txt).group(1);parent='';pagenum=0;prev=[]
  for page in txt.split('\f'):
   pagenum+=1
   for line in page.splitlines():
    raw=line.rstrip()
    if 'количество записей' in raw:
     parent=next((x.strip() for x in reversed(prev) if x.strip()),'');prev=[];continue
    prev.append(raw)
    m=re.match(r'^\s*(\d{7})\s{2,}(.+?)\s{2,}(.+?)\s{2,}(\d{2,3}°\d+(?:[.,]\d+)?\x27)\s+(\d{2,3}°\d+(?:[.,]\d+)?\x27)\s+(\S+)\s*$',raw)
    if not m:continue
    reg,name,typ,la,lo,mapcode=m.groups()
    def conv(s):d,mi=s[:-1].split('°');return int(d)+float(mi.replace(',','.'))/60
    rows.append(dict(region=region,registry_id=reg,name=name,formal_type_literal=typ,latitude_literal=la,longitude_literal=lo,lat=conv(la),lon=conv(lo),map_sheet=mapcode,administrative_attachment_literal=parent,registry_asof_date=date,pdf_page_1based=pagenum,raw_source_line=raw,source_pdf=str(pdf.relative_to(H)),source_pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),coordinate_measurement_date_unknown=True,displayed_unit='arcminute; 0.1 where displayed',registry_date_is_not_measurement_date=True,automatic_multiline_reconstruction=False))
 out=pd.DataFrame(rows);out.to_parquet(H/'primary_GKGN_published_coordinate_assertions.parquet',index=False)
 targets=pd.read_parquet(H/'all1767_native2021_geography_gaps_source_frame.parquet');a=pd.read_parquet(H/'dated_primary_and_geometry_validated_A_candidates_v2.parquet').set_index('id');cand=[]
 for z in targets.itertuples():
  hits=out[out.region.eq(z.region_source)&out.name.map(norm).eq(norm(z.name))&out.formal_type_literal.map(norm).eq(norm(z.type))]
  for q in hits.itertuples():
   v=a.loc[z.id] if z.id in a.index else None
   distance=None
   if v is not None:
    p1,p2=map(math.radians,[q.lat,v.source_lat]);dl=math.radians(q.lon-v.source_lon);dp=p1-p2;distance=6371*2*math.asin(math.sqrt(math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2))
   d=q._asdict();d.pop('Index');d.update(id=z.id,native_np_oktmo11=z.native_np_oktmo11,native2021_parent8=z.native_source_parent_oktmo8,native2021_parent_literal=z.mun_upper,population2021=z.population_2021,coordinate_missing=z.coordinate_missing,all_primary_GKGN_exact_region_typed_name_matches=len(hits),distance_km_to_coded_OSM_node=distance,identity_status='C_review_no_exact_code_or_dated_parent_bridge',axis_adopted=False);cand.append(d)
 c=pd.DataFrame(cand);c.to_parquet(H/'primary_GKGN_vs_native2021_candidate_coordinate_witnesses.parquet',index=False);r={'status':'PRIMARY_PUBLISHED_SOURCE_COORDINATES_SEPARATE_WITNESSES_NO_AXIS_ADOPTION','parsed_complete_single_line_records':len(out),'by_source':out.groupby(['region','registry_asof_date']).size().to_dict().__str__(),'native_target_source_assertions':len(c),'native_targets_with_at_least_one_registry_witness':c.id.nunique(),'no_identity_admission_without_exact_code_or_dated_parent_bridge':True,'no_nearest_coordinate_selection_or_averaging':True};(H/'primary_GKGN_coordinate_witness_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps(r,ensure_ascii=False))
if __name__=='__main__':main()
