"""Inspect an acquired PDF locally, preserving formfeed page boundaries."""
import argparse,subprocess,json,hashlib,re
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('pdf');a=p.parse_args();f=Path(a.pdf);out=f.with_suffix('.txt');subprocess.run(['pdftotext','-layout',str(f),str(out)],check=True)
pages=out.read_text().split('\f');hits=[]
for i,text in enumerate(pages,1):
 for m in re.finditer(r'(?:Численность населения по каждому|1959 по 1989|1989.{0,100}2002)',text,re.I):hits.append(dict(pdf_page=i,text=text[max(0,m.start()-100):m.end()+300]))
r=dict(path=str(f),sha256=hashlib.sha256(f.read_bytes()).hexdigest(),bytes=f.stat().st_size,pdf_pages=len(pages)-1 if not pages[-1].strip() else len(pages),hits=hits)
f.with_suffix('.inspection.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps(r,ensure_ascii=False,indent=2))
