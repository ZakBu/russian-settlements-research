"""Render pinned published files for actual visual inspection, without edits."""
from pathlib import Path
import argparse
import base64
import hashlib
import io
import json
import urllib.request
import fitz
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[3]
m=json.loads((ROOT/'research/ecommerce_cloud/continuation/published_visual_assets.json').read_text())
p=argparse.ArgumentParser();p.add_argument('--mode',choices=['pages','charts'],required=True)
p.add_argument('--group',type=int,required=True);a=p.parse_args()
def read(row):
    with urllib.request.urlopen(row['url'],timeout=45) as r:
        body=r.read(row['bytes']+1)
    assert len(body)==row['bytes'] and hashlib.sha256(body).hexdigest()==row['sha256']
    return body
def emit(im,name):
    out=io.BytesIO();im.convert('RGB').save(out,format='JPEG',quality=87,optimize=True)
    print('VISUAL_PREVIEW_BEGIN '+name,flush=True)
    print(base64.b64encode(out.getvalue()).decode(),flush=True)
    print('VISUAL_PREVIEW_END',flush=True)
if a.mode=='pages':
    row=next(x for x in m['assets'] if x['name'].endswith('.pdf'))
    doc=fitz.open(stream=read(row),filetype='pdf')
    assert len(doc)==m['pdf_pages']
    selected=list(range(a.group*5,min((a.group+1)*5,len(doc))))
    assert selected
    tiles=[]
    for index in selected:
        pix=doc[index].get_pixmap(dpi=95,alpha=False)
        im=Image.open(io.BytesIO(pix.tobytes('png'))).convert('RGB')
        im.thumbnail((750,1060))
        tile=Image.new('RGB',(780,1100),'#ededed')
        tile.paste(im,((780-im.width)//2,28))
        ImageDraw.Draw(tile).text((12,8),'Page '+str(index+1),fill='black')
        tiles.append(tile)
    cols=2;rows=(len(tiles)+1)//2
    canvas=Image.new('RGB',(cols*780,rows*1100),'white')
    for i,im in enumerate(tiles):
        canvas.paste(im,((i%cols)*780,(i//cols)*1100))
    emit(canvas,'pages-'+str(selected[0]+1)+'-'+str(selected[-1]+1))
else:
    rows=[x for x in m['assets'] if x['name'].endswith('.png')]
    selected=rows[a.group*3:(a.group+1)*3]
    assert selected
    for row in selected:
        im=Image.open(io.BytesIO(read(row))).convert('RGB')
        im.thumbnail((1500,1100))
        emit(im,row['name'])
print('VISUAL_SOURCE_CHECK '+json.dumps({'mode':a.mode,'group':a.group,'published_bytes_verified':True,
                                      'preview_is_not_an_edit_of_published_files':True}))
