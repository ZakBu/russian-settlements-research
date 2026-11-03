"""Independent postal-anchor PDF extraction, not drawn-cell parser reuse.

Postal codes anchor rows. All other words are assigned to nearest postal row
within the same page; this alternative is a cross-check of this specific PDF,
not a general replacement for explicit cell boundaries. No source parser imports.
"""
from pathlib import Path
import base64,collections,hashlib,json,re,subprocess,tempfile,unicodedata
import xml.etree.ElementTree as ET
import pandas as pd
ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
RAW=ROOT/'work/ecommerce_operations_20261104'
PDF=RAW/'sources/tariff_20230906185652.pdf'
NS={'h':'http://www.w3.org/1999/xhtml'}
def main():
    b=PDF.read_bytes()
    assert hashlib.sha256(b).hexdigest()=='2914616d3ca4874ad2e69b2ea31302147088559d02fb46f0f46b152ed2aa30f0'
    assert base64.b32encode(hashlib.sha1(b).digest()).decode().rstrip('=')=='FLZD62QBY2Y53AQWDNRPRK7HTNKVTWMM'
    with tempfile.TemporaryDirectory() as t:
        xml=Path(t)/'bbox.xml';subprocess.run(['pdftotext','-bbox',str(PDF),str(xml)],check=True);doc=ET.parse(xml)
    rows=[];maximum_distance=0;headers=0
    for pg,page in enumerate(doc.findall('.//h:page',NS),1):
        words=[]
        for w in page.findall('h:word',NS):
            x=(float(w.get('xMin'))+float(w.get('xMax')))/2
            y=(float(w.get('yMin'))+float(w.get('yMax')))/2
            words.append((x,y,w.text))
        anchors=sorted((y,text) for x,y,text in words if x>490 and re.fullmatch(r'\d{6}',text))
        assert anchors,(pg,'no postal anchors')
        assert len({y for y,code in anchors})==len(anchors)
        cells=[[[],[]] for _ in anchors]
        for x,y,text in words:
            if x>490 and re.fullmatch(r'\d{6}',text):continue
            if y<anchors[0][0]-12:
                headers+=1;continue
            nearest=min(range(len(anchors)),key=lambda i:abs(anchors[i][0]-y))
            distance=abs(anchors[nearest][0]-y);maximum_distance=max(maximum_distance,distance)
            assert distance<12,(pg,x,y,text,distance)
            assert x<490,(pg,x,y,text)
            cells[nearest][0 if x<240 else 1].append((y,x,text))
        for (y,postal),(left,name) in zip(anchors,cells):
            def join(c):return ' '.join(w[2] for w in sorted(c,key=lambda w:(round(w[0],1),w[1])))
            region=join(left);settlement=join(name)
            assert region and settlement
            lines=len({round(w[0],1) for w in name})
            rows.append((pg,region,settlement,postal,lines))
    published=pd.read_csv(RAW/'ozon_tariff_geography2023_all.csv',dtype={'postal_index2023':str})
    actual=list(published[['pdf_page','region2023','name2023','postal_index2023','name_cell_lines']].itertuples(index=False,name=None))
    assert len(actual)==len(rows)
    discrepancies=[(i+1,a,b) for i,(a,b) in enumerate(zip(rows,actual)) if a!=b]
    assert not discrepancies,discrepancies[:8]
    stats=dict(source_pages=len(doc.findall('.//h:page',NS)),extracted_rows=len(rows),distinct_region_labels=len({r[1] for r in rows}),multiline_name_rows=sum(r[4]>1 for r in rows),max_name_cell_lines=max(r[4] for r in rows),unique_region_name_postal_triples=len({r[1:4] for r in rows}))
    report=json.loads((HERE/'postal_geography2023_summary.json').read_text())
    for k,v in stats.items():assert report[k]==v,(k,report[k],v)
    def norm(x):return ' '.join(unicodedata.normalize('NFKC',str(x)).casefold().replace('ё','е').split())
    keys=collections.defaultdict(list)
    for r in published.itertuples():
        typ='' if pd.isna(r.type_wording2023) else r.type_wording2023
        if typ: assert r.name2023.startswith(typ+' ')
        base=r.name2023[len(typ):].strip() if typ else r.name2023
        assert base==r.name_without_type2023
        keys[(norm(r.region2023),norm(base))].append(r.row2023_n)
    old=pd.read_csv(HERE.parent/'next_direction_20261103/programme_pilot_row_disposition.csv')
    dispositions=pd.read_csv(HERE/'pilot_old_names_postal2023_disposition.csv')
    matches=pd.read_csv(HERE/'pilot_old_names_postal2023.csv')
    counts=collections.Counter();single=collections.Counter()
    for r in old.itertuples():
        expected=keys[(norm(r.region_source),norm(r.name_source))]
        out=dispositions.loc[dispositions.row2022_n.eq(r.row_n)]
        assert len(out)==1 and int(out.matches2023_n.iloc[0])==len(expected)
        got=matches.loc[matches.row2022_n.eq(r.row_n)]
        assert set(got.row2023_n)==set(expected)
        assert not got.identity2022_confirmed.any()
        label='zero' if not expected else 'one' if len(expected)==1 else 'multiple'
        counts[label]+=1
        if r.status=='single_exact_name_candidate_only':single[label]+=1
    assert dict(counts)==report['pilot_old_rows_match_counts']
    assert dict(single)==report['old_single_candidate_match_counts']
    assert len(matches)==report['pilot_2023_match_records']
    postal_counts=published.postal_index2023.value_counts()
    postal_reuse=dict(unique_postal_indices=len(postal_counts),shared_postal_indices=int((postal_counts>1).sum()),rows_sharing_postal_index=int(postal_counts[postal_counts>1].sum()),maximum_rows_per_postal_index=int(postal_counts.max()))
    assert postal_reuse==dict(unique_postal_indices=18498,shared_postal_indices=2681,rows_sharing_postal_index=6508,maximum_rows_per_postal_index=16)
    print(json.dumps(dict(**stats,postal_reuse=postal_reuse,pdf_sha256_matches=True,cdx_sha1_matches=True,independent_row_discrepancies=0,pilot_dispositions_checked=len(old),pilot_match_records_checked=len(matches),max_word_to_postal_anchor_distance=maximum_distance,excluded_header_words=headers,method='Poppler word positions, postal-code row anchors; no drawn borders or main parser imports'),ensure_ascii=False))
if __name__=='__main__':main()
