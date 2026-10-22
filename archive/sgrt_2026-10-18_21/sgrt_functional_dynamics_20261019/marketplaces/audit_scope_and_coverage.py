"""Rebuild read-only coverage and type-sensitivity audits from the frozen tables."""
from pathlib import Path
import collections,hashlib,json
import pandas as pd
R=Path(__file__).resolve().parent

def main():
    from build_marketplaces import source_bytes
    a=pd.read_parquet(R/'wb_delivery_locations_ru_20261019.parquet');f=a[a.focus_scope]
    p=pd.read_csv(R/'wb_pilot_all_delivery_locations.csv')
    z={'source_service_section':'ru, not a territorial RF mask','all_records':len(a),
       'all_linkage':a.link_status.value_counts().to_dict(),'all_matched_settlements':a.settlement_uid.nunique(),
       'focus_records':len(f),'focus_linkage':f.link_status.value_counts().to_dict(),'focus_matched_settlements':f.settlement_uid.nunique(),
       'pilot_all_records':len(p),'pilot_all_settlements':p.settlement_uid.nunique(),
       'pilot_all_by_municipal_context':p.groupby('pilot').size().to_dict(),
       'pilot_type_counts':{str(k):int(v)for k,v in p.groupby('typePoint').size().items()},
       'pilot_focus_records':int(p.focus_scope.sum()),'pilot_focus_settlements':p.loc[p.focus_scope,'settlement_uid'].nunique(),
       'pilot_settlement_loss_if_focus_only':p.settlement_uid.nunique()-p.loc[p.focus_scope,'settlement_uid'].nunique(),
       'objects_csv_sha256':hashlib.sha256((R/'objects.csv').read_bytes()).hexdigest(),
       'no_external_catchment_observed':True,
       'scope_limit':'All types include postal/unknown/technical locations; no automatic equivalence to general-public pickup points.'}
    (R/'COVERAGE.json').write_text(json.dumps(z,ensure_ascii=False,indent=2))
    rows=[]
    for mode,codes in [('all_published',None),('focus8_34',[8,34]),('non14_sensitivity',list(set(a.typePoint)-{14})),('expanded8_34_28_53_54',[8,34,28,53,54])]:
        s=a if codes is None else a[a.typePoint.isin(codes)];q=p if codes is None else p[p.typePoint.isin(codes)]
        rows.append(dict(mode=mode,provider_ru_records=len(s),name_coordinate_linked=int(s.settlement_uid.notna().sum()),
          linked_settlements=s.settlement_uid.nunique(),pilot_records=len(q),pilot_settlements=q.settlement_uid.nunique(),
          meaning='Source-section sensitivity only; no official exhaustive subtype dictionary or catchments'))
    pd.DataFrame(rows).to_csv(R/'type_sensitivity.csv',index=False)
    g=a[(a.latitude>75)|(a.longitude<20)].copy();g['scope_reason']='extreme_coordinate_screen_not_automatic_exclusion'
    g.loc[g.object_id.eq('wb:50080949'),'scope_reason']='Svalbard_Barentsburg_counterexample_country_ru_is_not_Russia_mask'
    g['geographic_claim']='Provider country section only; coordinates preserved';g.to_csv(R/'geographic_scope_audit.csv',index=False)
    raw=json.loads(source_bytes('wb_all_points_v11.json'));ru=next(c['items']for c in raw if c['country']=='ru')
    pd.DataFrame([dict(object_id='wb:'+str(x['id']),source_status=x.get('status'),typePoint=x.get('typePoint'),address=x.get('address'),
      status_meaning='unknown_do_not_infer_active_or_closed')for x in ru if 'status'in x]).to_csv(R/'provider_status_audit.csv',index=False)
    schema={'root_schema':'list of country blocks {country: string, items: list[object]}','provider_ru_section_rows':len(ru),
      'coordinate_order':['latitude','longitude'],'fields':{k:dict(collections.Counter(type(x.get(k)).__name__ for x in ru))for k in sorted(set(k for x in ru for k in x))},
      'decisions':{'id':'Provider identifier, not opening date','radius':'Not used as a scientific catchment radius',
      'typePoint':'All preserved; focus 8/34 and expanded modes are sensitivity only; no exhaustive official dictionary read',
      'workTime':'Published schedule, not verified operational status','fittingRooms':'Not demand, throughput or jobs',
      'country':'Provider service section, not geographic/jurisdictional mask; includes Barentsburg Svalbard'}}
    (R/'source_schema.json').write_text(json.dumps(schema,ensure_ascii=False,indent=2))
    print(json.dumps(z,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
