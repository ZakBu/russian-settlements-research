import csv
from pathlib import Path
from PIL import Image,ImageDraw
base=Path('/workspace/shared/extended-population-20261013');out=Path('/workspace/shared/rsfsr1989-urban-mass-20261013');rows=list(csv.DictReader(open('/workspace/russian-settlements-research/research_rebuild/evidence/extended_population_sources_20261013/bulk_ocr_locality_candidates.csv')));rows=[r for r in rows if (int(r['source_pdf_page_1based'])<123 or r['scan_side']=='left' and r['source_pdf_page_1based']=='123') and max([int(r[k]) if r[k] else 0 for k in ['population_1989_present_candidate','population_1989_permanent_candidate']])>=100000];crops=[]
for i,r in enumerate(rows):
 page=int(r['source_pdf_page_1based']);side=r['scan_side'];key=r['ocr_line_key'].split(':');words=[x for x in csv.DictReader((base/f'ocr_{page:03d}_{side}.tsv').open(),delimiter='\t',quoting=csv.QUOTE_NONE) if x['level']=='5' and [x['block_num'],x['par_num'],x['line_num']]==key];y=min(int(w['top']) for w in words);h=max(int(w['top'])+int(w['height']) for w in words)-y;im=Image.open(base/f'ocr_{page:03d}_{side}.png');crop=im.crop((0,max(0,y-5),im.width,min(im.height,y+h+5)));crops.append((i,r,crop))
for i in range((len(crops)+11)//12):
 group=crops[i*12:(i+1)*12];canvas=Image.new('RGB',(1962,sum(c.height*2+26 for *_,c in group)), 'white');draw=ImageDraw.Draw(canvas);y=0
 for idx,r,crop in group:
  draw.text((5,y),f'INDEX {idx} PDF{r["source_pdf_page_1based"]} {r["scan_side"]} {r["ocr_line_key"]}',fill='black');y+=24;canvas.paste(crop.resize((crop.width*2,crop.height*2)),(0,y));y+=crop.height*2+2
 canvas.save(out/f'city_candidates_{i:02d}.png')
with (out/'image_crop_row_index.csv').open('w') as f:w=csv.DictWriter(f,['index']+list(rows[0]));w.writeheader();w.writerows({'index':i,**r} for i,r in enumerate(rows))
print(len(rows))
