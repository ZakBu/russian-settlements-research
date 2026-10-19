"""Independent read-only audit of recovered GitHub Actions output, not raw RFSD."""
from pathlib import Path
import io, json, hashlib, zipfile
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
PATH = ROOT / 'SGRT_RFSD_RECOVERED.zip'
EXPECTED_SHA = 'a1f4cf310b3fac8d0fd5cf2375e203ed7c589fbef7cabe05a52e7ab2fb33a6ef'
YEARS = [2017,2018,2019,2020,2022,2023,2024,2025]
checks=[]
def check(name, ok, **details):
    checks.append({'name': name, 'pass': bool(ok), **details})

sha=hashlib.sha256(PATH.read_bytes()).hexdigest()
check('archive_sha256',sha==EXPECTED_SHA,actual=sha,expected=EXPECTED_SHA)
frames={}
with zipfile.ZipFile(PATH) as z:
    check('zip_crc_all_members',z.testzip() is None,members=len(z.namelist()))
    provenance=json.loads(z.read('coverage_provenance.json'))
    check('provenance_year_set',sorted(x['year'] for x in provenance)==YEARS)
    for p in provenance:
        check(f"provenance_source_digest_{p['year']}",p['source_sha256']==p['source_expected_sha256'])
        check(f"provenance_source_size_{p['year']}",p['bytes_transferred']==p['source_expected_bytes'])
        check(f"provenance_status_{p['year']}",p['status']=='ok')
    for name in ['zone_financial','localfirst_financial','zone_sectors','localfirst_sectors']:
        d=pd.read_parquet(io.BytesIO(z.read(name+'.parquet')))
        csv=pd.read_csv(io.BytesIO(z.read(name+'.csv')),dtype={'center_id':str,'okved_section':str},keep_default_na=False)
        frames[name]=d
        keys=['center_id','year']
        keys+=['selection'] if name=='zone_financial' else ['max_distance_km','quality'] if name=='localfirst_financial' else ['okved_section']
        check(name+'_fully_readable',True,rows=len(d),columns=d.columns.tolist())
        check(name+'_year_set',sorted(d.year.unique().tolist())==YEARS)
        check(name+'_unique_aggregate_keys',not d.duplicated(keys).any(),keys=keys,duplicates=int(d.duplicated(keys).sum()))
        check(name+'_no_missing_keys',not d[keys].isna().any().any())
        check(name+'_positive_integral_orgcounts',bool((d.n_organizations>0).all() and (d.n_organizations%1==0).all()))
        check(name+'_csv_shape',csv.shape==d.shape,csv_rows=len(csv))
        a=d.sort_values(keys).reset_index(drop=True);b=csv.sort_values(keys).reset_index(drop=True)
        differences={}
        for col in d.columns:
            if pd.api.types.is_numeric_dtype(d[col]):
                v=pd.to_numeric(b[col],errors='coerce').to_numpy()
                ok=np.allclose(a[col].to_numpy(),v,rtol=1e-12,atol=1e-7,equal_nan=True)
                if not ok: differences[col]=int((~np.isclose(a[col].to_numpy(),v,rtol=1e-12,atol=1e-7,equal_nan=True)).sum())
            elif not a[col].fillna('').astype(str).equals(b[col].fillna('').astype(str)):
                differences[col]='string mismatch'
        check(name+'_csv_parquet_complete_equality',not differences,differences=differences,rtol=1e-12,atol=1e-7)
        if 'top_firm_revenue_share' in d:
            vals=d.top_firm_revenue_share.dropna()
            check(name+'_topfirm_share_bounds',((vals>=-1e-12)&(vals<=1+1e-12)).all())

for p in provenance:
    year=p['year'];c=p['coverage']
    for selection in ['baseline','strict_house_nonimputed','house_or_street','all_outliers_included']:
        d=frames['zone_financial'];d=d[(d.year==year)&(d.selection==selection)]
        key='baseline_n' if selection=='baseline' else selection+'_n'
        revenuekey='baseline_revenue' if selection=='baseline' else selection+'_revenue'
        check(f'zone_org_balance_{year}_{selection}',int(d.n_organizations.sum())==c[key],actual=int(d.n_organizations.sum()),expected=c[key])
        check(f'zone_revenue_balance_{year}_{selection}',np.isclose(d.revenue_thousand_rub_nominal.sum(),c[revenuekey],rtol=1e-12,atol=.01))
    for quality in ['baseline','strict']:
        for radius in [1,5,10]:
            d=frames['localfirst_financial'];d=d[(d.year==year)&(d.quality==quality)&(d.max_distance_km==radius)]
            key=f'localfirst_{quality}_{radius}km'
            check(f'localfirst_org_balance_{year}_{quality}_{radius}',int(d.n_organizations.sum())==c[key+'_n'],actual=int(d.n_organizations.sum()),expected=c[key+'_n'])
            check(f'localfirst_revenue_balance_{year}_{quality}_{radius}',np.isclose(d.revenue_thousand_rub_nominal.sum(),c[key+'_revenue'],rtol=1e-12,atol=.01))
    for sectors,financial,query in [('zone_sectors','zone_financial',lambda d:d.selection=='baseline'),('localfirst_sectors','localfirst_financial',lambda d:(d.quality=='baseline')&(d.max_distance_km==5))]:
        s=frames[sectors];s=s[s.year==year].groupby('center_id')[['n_organizations','revenue_thousand_rub_nominal']].sum()
        f=frames[financial];f=f[(f.year==year)&query(f)].set_index('center_id')[['n_organizations','revenue_thousand_rub_nominal']]
        a=s.reindex(f.index).fillna(0)
        check(f'{sectors}_baseline_org_partition_{year}',a.n_organizations.equals(f.n_organizations),sector_total=int(s.n_organizations.sum()),financial_total=int(f.n_organizations.sum()),extra_centres=int(len(s.index.difference(f.index))))
        check(f'{sectors}_baseline_revenue_partition_{year}',np.allclose(a.revenue_thousand_rub_nominal,f.revenue_thousand_rub_nominal,rtol=1e-12,atol=.01))

report={'archive':PATH.name,'sha256':sha,'scope':'Recovered eight-year aggregate artifact only; source digest claims compared with embedded provenance, raw source bytes not re-downloaded in this audit. Not the complete 2011–2025 layer or adjudicated final 2010 model.','years':YEARS,'checks':checks,'passed':sum(c['pass'] for c in checks),'failed':sum(not c['pass'] for c in checks)}
(ROOT/'rfsd_independent_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({'passed':report['passed'],'failed':report['failed'],'failures':[c for c in checks if not c['pass']]},ensure_ascii=False))
