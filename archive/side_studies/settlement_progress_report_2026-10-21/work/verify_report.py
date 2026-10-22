from pathlib import Path
from zipfile import ZipFile
import pandas as pd,json,hashlib
from lxml import etree
from pypdf import PdfReader
root=Path.cwd();old=Path('data');d=pd.read_parquet(old/'localities.parquet');s=json.load(open(old/'summary.json'))
pair=d.p2002.notna()&d.p2021.notna();assert pair.sum()==143446
assert (d.loc[pair,'p2021']<d.loc[pair,'p2002']).sum()==107921
assert (d.loc[pair,'p2021']>d.loc[pair,'p2002']).sum()==26437
assert (d.loc[pair,'p2021']==d.loc[pair,'p2002']).sum()==9088
assert ((d.p2002>0)&d.p2021.eq(0)).sum()==14110
assert d[['p2002','p2010','p2021']].notna().all(axis=1).sum()==142765
assert sum(s['coverage'][i]['coverage_percent']>99.5 for i in range(3))==3
r=Path('work/sources/research/sgrt_word_completion_20261021');counts=pd.read_csv('work/service_counts.csv');assert counts.NP_strict.ge(0).all()
for family in ['education','medical','commerce']:
 t=pd.read_parquet(r/f'model_inputs_cycle05/relinked_v4/{family}/settlement_features_full_axis.parquet');assert len(t)==173862 and t.id.is_unique
c=pd.read_parquet('work/sources/commerce_current.parquet');assert c.id.is_unique;assert c.commerce_wb20261021_baseline_focus_count.gt(0).sum()==7991;assert c.commerce_ozon_name_signal_not_verified_pvz_count.gt(0).sum()==31
p=next(Path('outputs').glob('*.docx'));ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
with ZipFile(p) as z:
 assert z.testzip() is None
 xml=etree.fromstring(z.read('word/document.xml'));txt=' '.join(xml.xpath('//w:t/text()',namespaces=ns));assert all(q in txt for q in ['ФАПы','Образование','Коммерция','Крыма и Севастополя','карта выше','1 минус отношение'])
 styles=etree.fromstring(z.read('word/styles.xml'));assert not styles.xpath('//w:style[@w:styleId="Title"]//w:pBdr',namespaces=ns)
 assert not xml.xpath('//w:ins|//w:del',namespaces=ns)
 links=etree.fromstring(z.read('word/_rels/document.xml.rels'));assert len([v for v in links if v.get('TargetMode')=='External'])==7
pdf=next(Path('outputs').glob('*.pdf'));pr=PdfReader(pdf);assert len(pr.pages)==15
# Page-image inspection is recorded separately in provenance/editorial_review.md.
manifest=[]
for f in Path('work/sources').rglob('*'):
 if f.is_file():manifest.append({'path':str(f),'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()})
Path('work/downloaded_source_manifest.json').write_text(json.dumps({'main_commit':s['commit'],'research_commit':'d86b2f8b0144537c1bb8348b7f6d320fe844e835','files':manifest},ensure_ascii=False,indent=2))
result={'status':'passed','pages':15,'docx':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'checks':['demographic counts','coverage arithmetic','unique service axes','WB/Ozon counts','DOCX archive integrity','title border removed','version and caveat text','source hyperlinks','15 PDF pages']};Path('work/verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False,indent=2))
