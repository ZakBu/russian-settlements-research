"""Render the accepted research-stage text with embedded Cyrillic fonts."""
from __future__ import annotations
import argparse,hashlib,json,re,html
from pathlib import Path
from matplotlib.font_manager import findfont,FontProperties
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,Image
from reportlab.lib.pagesizes import A4
from pypdf import PdfReader


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parent);a=ap.parse_args();r=a.root
    out=r/'output/pdf';out.mkdir(parents=True,exist_ok=True)
    for name,weight in [('DV','normal'),('DVB','bold')]:pdfmetrics.registerFont(TTFont(name,findfont(FontProperties(family='DejaVu Sans',weight=weight))))
    pdfmetrics.registerFontFamily('DV',normal='DV',bold='DVB',italic='DV',boldItalic='DVB')
    base=ParagraphStyle('Body',fontName='DV',fontSize=9,leading=13,spaceAfter=6,textColor=colors.HexColor('#20384a'))
    heads={1:ParagraphStyle('H1',parent=base,fontName='DVB',fontSize=18,leading=22,spaceAfter=14,keepWithNext=True),2:ParagraphStyle('H2',parent=base,fontName='DVB',fontSize=13,leading=17,spaceBefore=10,spaceAfter=8,keepWithNext=True),3:ParagraphStyle('H3',parent=base,fontName='DVB',fontSize=10.5,leading=14,spaceBefore=8,spaceAfter=6,keepWithNext=True)}
    cell=ParagraphStyle('Cell',parent=base,fontSize=7.2,leading=10,spaceAfter=0)
    def inline(s):
        s=html.escape(s)
        s=re.sub(r'\*\*(.*?)\*\*',r'<b>\1</b>',s)
        s=re.sub(r'`([^`]+)`',r'<font color="#286f97">\1</font>',s)
        s=re.sub(r'\[([^\]]+)\]\(([^)]+)\)',r'\1',s)
        return s
    story=[];lines=(r/'RESULTS.md').read_text().splitlines();i=0
    while i<len(lines):
        s=lines[i].strip()
        if not s:i+=1;continue
        if s.startswith('|'):
            rows=[]
            while i<len(lines) and lines[i].strip().startswith('|'):
                row=lines[i].strip().strip('|').split('|');i+=1
                if all(re.fullmatch(r'[\s:\-]+',x) for x in row):continue
                rows.append([Paragraph(inline(x.strip()),cell) for x in row])
            n=len(rows[0]);width=(A4[0]-100)/n
            t=Table(rows,colWidths=[width]*n,repeatRows=1,hAlign='LEFT')
            t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#d9e8f0')),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f0f5f8')]),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]));story.extend([t,Spacer(1,10)]);continue
        if s.startswith('!['):
            target=re.search(r'\]\(([^)]+)\)',s).group(1);im=Image(str(r/target));iw,ih=im.imageWidth,im.imageHeight;im.drawWidth=A4[0]-100;im.drawHeight=ih/iw*im.drawWidth;story.extend([im,Spacer(1,8)]);i+=1;continue
        if s.startswith('#'):
            level=min(len(s)-len(s.lstrip('#')),3);story.append(Paragraph(inline(s.lstrip('#').strip()),heads[level]));i+=1;continue
        buf=[s];i+=1
        while i<len(lines) and lines[i].strip() and not lines[i].strip().startswith(('#','|','![')):
            buf.append(lines[i].strip());i+=1
        story.append(Paragraph(inline(' '.join(buf)),base))
    def footer(c,doc):
        c.setStrokeColor(colors.HexColor('#b0c5d2'));c.line(41,34,A4[0]-41,34);c.setFont('DV',7);c.setFillColor(colors.HexColor('#536e80'));c.drawString(41,23,'Опорность НП | Проверенный функциональный пилот | 19.10.2026');c.drawRightString(A4[0]-41,23,str(doc.page))
    p=out/'ANCHOR_RESEARCH_STAGE1.pdf';SimpleDocTemplate(str(p),pagesize=A4,rightMargin=41,leftMargin=41,topMargin=36,bottomMargin=45,title='Опорность населённых пунктов: исследовательский пилот',author='Исследовательский проект Захара Бучинцева').build(story,onFirstPage=footer,onLaterPages=footer)
    meta={'source_sha256':hashlib.sha256((r/'RESULTS.md').read_bytes()).hexdigest(),'pdf_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'pages':len(PdfReader(p).pages),'bytes':p.stat().st_size}
    (out/'manifest.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n');print(json.dumps(meta))


if __name__=='__main__':main()
