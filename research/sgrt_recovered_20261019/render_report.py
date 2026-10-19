"""Render the frozen Russian scientific report, inspectable tables and source figures."""
from pathlib import Path
import argparse, hashlib, html, json, re
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4
from PIL import Image as PILImage
from pypdf import PdfReader, PdfWriter
R=Path(__file__).resolve().parent
ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,default=R/'report/REPORT.md');ap.add_argument('--out',type=Path,default=R/'report/SGRT_RESEARCH_REPORT.pdf');a=ap.parse_args()
text=a.source.read_text()
for pattern in ['_PENDING','RFSD_FINAL_','BIBLIOGRAPHY_FINAL','MAPS_FUNCTIONAL','MAPS_В','ILLUSTRATIVE_FINAL']:
    assert pattern not in text,('Unresolved manuscript marker',pattern)
from matplotlib.font_manager import findfont,FontProperties
for name,weight,style in [('DV','normal','normal'),('DV-Bold','bold','normal'),('DV-Italic','normal','oblique'),('DV-BoldItalic','bold','oblique')]:
    pdfmetrics.registerFont(TTFont(name,findfont(FontProperties(family='DejaVu Sans',weight=weight,style=style))))
pdfmetrics.registerFontFamily('DV',normal='DV',bold='DV-Bold',italic='DV-Italic',boldItalic='DV-BoldItalic')
S={}
S['body']=ParagraphStyle('body',fontName='DV',fontSize=9.5,leading=13.7,spaceAfter=5,textColor=HexColor('#172d3c'),splitLongWords=1,allowWidows=0,allowOrphans=0)
S['h1']=ParagraphStyle('h1',parent=S['body'],fontName='DV-Bold',fontSize=19,leading=24,spaceAfter=12,keepWithNext=True)
S['h2']=ParagraphStyle('h2',parent=S['body'],fontName='DV-Bold',fontSize=13,leading=17,spaceBefore=12,spaceAfter=7,keepWithNext=True,textColor=HexColor('#154f77'))
S['h3']=ParagraphStyle('h3',parent=S['body'],fontName='DV-Bold',fontSize=10.3,leading=14.5,spaceBefore=8,spaceAfter=5,keepWithNext=True)
S['table']=ParagraphStyle('table',parent=S['body'],fontSize=7.6,leading=10.7,spaceAfter=0)
S['thead']=ParagraphStyle('thead',parent=S['table'],fontName='DV-Bold',textColor=white)
S['caption']=ParagraphStyle('caption',parent=S['body'],fontSize=8.2,leading=11.6,textColor=HexColor('#466278'),spaceAfter=9)
S['code']=ParagraphStyle('code',parent=S['body'],fontSize=7.8,leading=11.1,backColor=HexColor('#eef3f6'),borderPadding=6,spaceBefore=3,spaceAfter=6)
def inline(t):
    t=t.replace('—','-').replace('–','-').replace('\u2011','-');t=html.escape(t)
    t=re.sub(r'\*\*(.+?)\*\*',r'<b>\1</b>',t);t=re.sub(r'`([^`]+)`',r'<font color="#345d78">\1</font>',t)
    t=re.sub(r'\[([^\]]+)\]\((https?[^)]+)\)',r'<link href="\2" color="#176599">\1</link>',t)
    t=re.sub(r'\[([^\]]+)\]\(([^)]+)\)',r'\1',t)
    return t
story=[];figures=[];lines=text.splitlines();i=0;W=A4[0]-90
def para(t,style='body'):return Paragraph(inline(t),S[style])
while i<len(lines):
    line=lines[i].strip()
    if not line:i+=1;continue
    if line.startswith('```'):
        block=[];i+=1
        while i<len(lines) and not lines[i].strip().startswith('```'):block.append(lines[i]);i+=1
        for b in block:story.append(para(b,'code'))
        i+=1;continue
    image=re.match(r'!\[([^\]]*)\]\(([^)]+)\)',line)
    if image:
        p=(a.source.parent/image.group(2)).resolve();assert p.exists(),p
        with PILImage.open(p) as im:im.load();width,height=im.size
        h=W*height/width
        story.append(Image(str(p),width=W,height=h));story.append(para(image.group(1),'caption'));figures.append(str(p.relative_to(R)));i+=1;continue
    if line.startswith('|'):
        rows=[]
        while i<len(lines) and lines[i].strip().startswith('|'):
            row=[s.strip() for s in lines[i].strip().strip('|').split('|')]
            if not all(re.fullmatch(r'[:\- ]+',s or '-') for s in row):rows.append(row)
            i+=1
        n=max(map(len,rows));assert all(len(r)==n for r in rows)
        lengths=[max(len(r[k]) for r in rows) for k in range(n)];weights=[min(max(v,10),48) for v in lengths]
        widths=[W*v/sum(weights) for v in weights]
        data=[[para(cell,'thead' if j==0 else 'table') for cell in row] for j,row in enumerate(rows)]
        table=Table(data,colWidths=widths,repeatRows=1,hAlign='LEFT')
        table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),HexColor('#1a4a6d')),('ROWBACKGROUNDS',(0,1),(-1,-1),[white,HexColor('#f0f4f7')]),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),('LINEBELOW',(0,0),(-1,0),.4,HexColor('#9eb0bf'))]))
        story.extend([table,Spacer(1,7)]);continue
    heading=re.match(r'^(#{1,3})\s+(.*)',line)
    if heading:story.append(para(heading.group(2),'h'+str(len(heading.group(1)))));i+=1;continue
    if line.startswith('- '):story.append(para('• '+line[2:]));i+=1;continue
    group=[line];i+=1
    while i<len(lines) and lines[i].strip() and not re.match(r'^(#|\||```|!\[|- )',lines[i].strip()):group.append(lines[i].strip());i+=1
    story.append(para(' '.join(group)))

def footer(canvas,doc):
    canvas.setStrokeColor(HexColor('#b6c5ce'));canvas.line(45,32,A4[0]-45,32);canvas.setFont('DV',7);canvas.setFillColor(HexColor('#536e80'));canvas.drawString(45,21,'Динамическая типология СГРТ | Проверенные расчёты 19.10.2026');canvas.drawRightString(A4[0]-45,21,str(doc.page))
a.out.parent.mkdir(exist_ok=True);body=a.out.with_name('report_body.tmp.pdf')
doc=SimpleDocTemplate(str(body),pagesize=A4,leftMargin=45,rightMargin=45,topMargin=42,bottomMargin=43,title='Динамическая типология сельско-городских районов тяготения России',author='Исследовательский проект Захара Бучинцева',pageCompression=1)
doc.build(story,onFirstPage=footer,onLaterPages=footer)
reader=PdfReader(body);assert len(reader.pages)>8
writer=PdfWriter();writer.append(reader)
# Original large-format maps remain readable vector/raster mixed appendices at native size.
appendices=[]
for name in ['04_center_environment.pdf','09_agricultural_profile.pdf','10_reporting_economic_profile.pdf']:
    p=R/'maps'/name;assert p.exists();writer.append(p);appendices.append('maps/'+name)
temp=a.out.with_suffix('.tmp.pdf')
with temp.open('wb') as f:writer.write(f)
finished=PdfReader(temp);assert len(finished.pages)==len(reader.pages)+3;temp.replace(a.out)
receipt={'source_sha256':hashlib.sha256(a.source.read_bytes()).hexdigest(),'pdf_sha256':hashlib.sha256(a.out.read_bytes()).hexdigest(),'bytes':a.out.stat().st_size,'pages':len(finished.pages),'body_pages':len(reader.pages),'figures':figures,'appendices':appendices}
(a.out.parent/'pdf_build.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps(receipt,ensure_ascii=False))
