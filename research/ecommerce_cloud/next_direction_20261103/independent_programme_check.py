"""Independent PDF geometry extraction and exact-name candidate audit; aggregates only."""
from pathlib import Path
import base64,collections,gzip,hashlib,json,re,subprocess,tempfile,unicodedata
import xml.etree.ElementTree as ET
import pandas as pd
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
WORK=ROOT/'work/ecommerce_next_20261103/identification'
def canonical(x):
    return ' '.join(unicodedata.normalize('NFKC',str(x)).lower().replace('ё','е').split())
def main():
    pdf=WORK/'tariff_20221022001416.pdf';blob=pdf.read_bytes()
    digest=base64.b32encode(hashlib.sha1(blob).digest()).decode().strip('=')
    assert digest=='FCWJI3NJ4DCISLCL72L43B5OGR7MCZ3Q'
    wire=(WORK/'business_js_wire.gz').read_bytes()
    assert base64.b32encode(hashlib.sha1(wire).digest()).decode().rstrip('=')=='HCFNP2P5MLIH77EVRJFWJVVBPDTTXBKT'
    js=(WORK/'business_20230219074750_92c4991.js').read_bytes()
    assert gzip.decompress(wire)==js
    assert b'last_mile/list_of_territories.pdf' in js
    with tempfile.TemporaryDirectory() as tmp:
        target=Path(tmp)/'bbox.xml'
        subprocess.run(['pdftotext','-bbox',str(pdf),str(target)],check=True)
        doc=ET.parse(target)
    ns={'h':'http://www.w3.org/1999/xhtml'};rows=[]
    pages=doc.findall('.//h:page',ns)
    for pg,page in enumerate(pages,1):
        lines=collections.defaultdict(list)
        for word in page.findall('h:word',ns):
            lines[round(float(word.attrib['yMin']),2)].append((float(word.attrib['xMin']),float(word.attrib['xMax']),word.text))
        for y,words in sorted(lines.items()):
            words.sort()
            if any(w[2]=='Регион' for w in words) and any(w[2]=='Населённый' for w in words):continue
            assert len(words)>=2,(pg,y,words)
            gaps=[words[i+1][0]-words[i][1] for i in range(len(words)-1)]
            cut=max(range(len(gaps)),key=gaps.__getitem__)+1
            assert gaps[cut-1]>10,(pg,y,words)
            rows.append((pg,' '.join(w[2] for w in words[:cut]),' '.join(w[2] for w in words[cut:])))
    published=pd.read_csv(WORK/'eligibility_20221022_rows.csv')
    assert rows==list(published[['pdf_page','region_source','name_source']].itertuples(index=False,name=None))
    multiplicity=collections.Counter((r,canonical(n)) for _,r,n in rows)
    actual=json.loads((HERE/'eligibility_list_summary2022.json').read_text())
    expected=dict(list_rows_n=len(rows),distinct_literal_region_labels_n=len({r for _,r,n in rows}),unique_region_normalized_name_pairs_n=len(multiplicity),repeated_pairs_n=sum(v>1 for v in multiplicity.values()),rows_in_repeated_pairs_n=sum(v for v in multiplicity.values() if v>1))
    for k,v in expected.items():assert actual[k]==v,(k,actual[k],v)
    axis=pd.read_parquet(ROOT/'work/sources/research/ecommerce_settlement_20261024/national/national_target_source2021.parquet')
    axis['key']=axis.name_2021.map(canonical)
    links=pd.read_csv(HERE/'programme_pilot_row_disposition.csv');checked=0
    summaries=pd.read_csv(HERE/'programme_pilot_summary.csv')
    for _,summary in summaries.iterrows():
        region=summary.region_source;base_region=canonical(region).removesuffix(' область').removesuffix(' край')
        if region=='Республика Саха (Якутия)':base_region='саха якутия'
        a=axis.loc[axis.region_2021.eq(base_region)]
        groups={k:g for k,g in a.groupby('key')}
        pop=[];statuses=collections.Counter();names=set()
        for row_number,(_,r,n) in enumerate(rows,1):
            if r!=region:continue
            key=canonical(n);names.add(key);g=groups.get(key);count=0 if g is None else len(g)
            status=('repeated_source_name' if multiplicity[(r,key)]>1 else 'no_exact_name' if count==0 else 'multiple_exact_names' if count>1 else 'single_exact_name_candidate_only')
            statuses[status]+=1
            output=links.loc[links.row_n.eq(row_number)]
            assert len(output)==1 and output.status.eq(status).all()
            assert output.exact_base_candidates_n.eq(count).all()
            assert not output.confirmed_identity.any()
            if status=='single_exact_name_candidate_only':
                record=g.iloc[0];pop.append(float(record.population_2021))
                assert output.candidate_id.eq(record.source_record_id_2021).all()
                assert output.candidate_population2021.eq(record.population_2021).all()
            checked+=1
        values=dict(base_settlements_n=len(a),source_rows_n=sum(statuses.values()),source_distinct_names_n=len(names),single_candidates_population2021_below1000_n=sum(v<1000 for v in pop),single_candidates_population2021_1000_to3500_n=sum(1000<=v<=3500 for v in pop),single_candidates_population2021_above3500_n=sum(v>3500 for v in pop),confirmed_identities_n=0)
        values.update({k+'_rows_n':statuses[k] for k in ('single_exact_name_candidate_only','multiple_exact_names','repeated_source_name','no_exact_name')})
        for key,value in values.items():assert summary[key]==value,(region,key,value)
    stress=pd.read_csv(HERE/'programme_pilot_wording_stress_tests.csv')
    taras=axis.loc[axis.region_2021.eq('нижегородская') & axis.name_2021.isin(['Тарасиха','станции Тарасиха'])]
    assert len(taras)==2 and set(taras.population_2021)=={2,1547}
    assert set(taras.source_record_id_2021)==set(stress.loc[stress.name_source.eq('Тарасиха'),'candidate_id'])
    print(json.dumps(dict(pdf_pages=len(pages),pdf_rows_independently_reconstructed=len(rows),cdx_sha1_matches=True,js_wire_cdx_sha1_matches=True,js_gunzip_matches=True,parser_discrepancies=0,pilot_rows_independently_checked=checked,**expected),ensure_ascii=False))
if __name__=='__main__':main()
