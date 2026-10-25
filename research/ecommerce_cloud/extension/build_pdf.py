"""Render the scientific manuscript and the independent review, without a web app.

The requested repository manuscript is the authoritative report. This is its
reading/export surface, not a separately authored analytical document.
"""
from pathlib import Path
from html import escape
import re
from markdown_it import MarkdownIt
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PIL import Image as PILImage
from matplotlib.font_manager import FontProperties, findfont

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
MANUSCRIPT=HERE.parent/'REPORT_RU.md'
REVIEW=HERE/'review/FINAL_CRITICAL_REVIEW.md'
OUT=ROOT/'work/ecommerce_cloud_extension/report'
OUT.mkdir(parents=True,exist_ok=True)
for name,family,weight,style in [('Body','DejaVu Sans','normal','normal'),('BodyBold','DejaVu Sans','bold','normal'),
    ('BodyItalic','DejaVu Sans','normal','oblique'),('Code','DejaVu Sans Mono','normal','normal')]:
    font=findfont(FontProperties(family=family,weight=weight,style=style),fallback_to_default=False)
    pdfmetrics.registerFont(TTFont(name,font))
pdfmetrics.registerFontFamily('Body',normal='Body',bold='BodyBold',italic='BodyItalic',boldItalic='BodyBold')
blue=colors.HexColor('#174f7b')
styles={
 'body':ParagraphStyle('body',fontName='Body',fontSize=9.6,leading=14.1,spaceAfter=7,splitLongWords=True,allowWidows=0,allowOrphans=0),
 'title':ParagraphStyle('title',fontName='BodyBold',fontSize=21,leading=27,textColor=blue,spaceAfter=17),
 'h2':ParagraphStyle('h2',fontName='BodyBold',fontSize=14,leading=18,textColor=blue,spaceBefore=15,spaceAfter=9,keepWithNext=True),
 'h3':ParagraphStyle('h3',fontName='BodyBold',fontSize=11,leading=15,textColor=blue,spaceBefore=12,spaceAfter=7,keepWithNext=True),
 'small':ParagraphStyle('small',fontName='Body',fontSize=8,leading=11,spaceAfter=7,textColor=colors.HexColor('#535b65')),
 'cell':ParagraphStyle('cell',fontName='Body',fontSize=7.4,leading=10.1,splitLongWords=True),
 'head':ParagraphStyle('head',fontName='BodyBold',fontSize=7.4,leading=10.1,textColor=colors.white),
 'code':ParagraphStyle('code',fontName='Code',fontSize=6.8,leading=9,spaceAfter=8,splitLongWords=True),
}

def inline(children):
    result=[]
    for t in children or []:
        if t.type=='text':result.append(escape(t.content))
        elif t.type=='code_inline':
            content=escape(t.content)
            if len(content)>45:content=content.replace('/','/\u200b').replace('_','_\u200b')
            result.append(f'<font name="Code" size="8">{content}</font>')
        elif t.type=='strong_open':result.append('<b>')
        elif t.type=='strong_close':result.append('</b>')
        elif t.type=='em_open':result.append('<i>')
        elif t.type=='em_close':result.append('</i>')
        elif t.type=='link_open':
            u=t.attrGet('href')
            if u.startswith(('https://','http://')):result.append(f'<a href="{escape(u,quote=True)}" color="#2166a7">')
            else:result.append('<font color="#2166a7">')
        elif t.type=='link_close':
            # All links in the report are flat; choose the last opening tag.
            openings=''.join(result)
            result.append('</a>' if openings.rfind('<a ')>openings.rfind('<font color=') else '</font>')
        elif t.type in ('softbreak','hardbreak'):result.append(' ')
    return ''.join(result)

def parse(path):
    tokens=MarkdownIt('default').parse(path.read_text())
    story=[];i=0;listdepth=0
    while i<len(tokens):
        t=tokens[i]
        if t.type=='heading_open':
            tag=t.tag
            text=inline(tokens[i+1].children)
            if tag=='h2' and text.startswith('11. '):story.append(PageBreak())
            sty='title' if tag=='h1' else 'h2' if tag=='h2' else 'h3'
            story.append(Paragraph(text,styles[sty]));i+=3;continue
        if t.type=='paragraph_open':
            tok=tokens[i+1]
            img=next((a for a in tok.children or [] if a.type=='image'),None)
            if img:
                p=(path.parent/img.attrGet('src')).resolve()
                if not p.exists():raise FileNotFoundError(p)
                with PILImage.open(p) as im:w,h=im.size
                width=17*cm;height=width*h/w
                if height>11.6*cm:height=11.6*cm;width=height*w/h
                story.extend([Spacer(1,5),Image(str(p),width=width,height=height),Spacer(1,10)])
            else:
                text=inline(tok.children)
                if listdepth:text='• '+text
                story.append(Paragraph(text,styles['body']))
            i+=3;continue
        if t.type in ('bullet_list_open','ordered_list_open'):listdepth+=1
        elif t.type in ('bullet_list_close','ordered_list_close'):listdepth-=1
        elif t.type=='table_open':
            rows=[];row=[];j=i+1
            while tokens[j].type!='table_close':
                a=tokens[j]
                if a.type=='tr_open':row=[]
                elif a.type=='inline':row.append(inline(a.children))
                elif a.type=='tr_close':rows.append(row)
                j+=1
            n=len(rows[0]);width=17*cm
            fractions=([.28,.72] if n==2 else [.30]+[.70/(n-1)]*(n-1))
            data=[[Paragraph(cell,styles['head' if k==0 else 'cell']) for cell in row] for k,row in enumerate(rows)]
            table=Table(data,colWidths=[width*f for f in fractions],repeatRows=1,hAlign='LEFT')
            table.setStyle(TableStyle([
                ('BACKGROUND',(0,0),(-1,0),blue),('VALIGN',(0,0),(-1,-1),'TOP'),
                ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.HexColor('#f0f4f7'),colors.white]),
                ('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),
                ('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),
                ('LINEBELOW',(0,-1),(-1,-1),.4,colors.HexColor('#bccad7'))]))
            story.extend([Spacer(1,4),table,Spacer(1,10)]);i=j+1;continue
        elif t.type=='fence':story.append(Paragraph(escape(t.content).replace('\n','<br/>'),styles['code']))
        i+=1
    return story

def footer(canvas,doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor('#d1dce5'));canvas.line(2*cm,1.65*cm,19*cm,1.65*cm)
    canvas.setFont('Body',7.2);canvas.setFillColor(colors.HexColor('#5c6670'))
    canvas.drawString(2*cm,1.18*cm,'Маркетплейсы и средние центры России · 25 октября 2026')
    canvas.drawRightString(19*cm,1.18*cm,str(doc.page));canvas.restoreState()

story=parse(MANUSCRIPT)
if REVIEW.exists():story.extend([PageBreak()]+parse(REVIEW))
pdf=OUT/'Marketplaces_and_Russian_Centres_20261025.pdf'
doc=SimpleDocTemplate(str(pdf),pagesize=(21*cm,29.7*cm),leftMargin=2*cm,rightMargin=2*cm,
    topMargin=1.8*cm,bottomMargin=2.05*cm,title='Маркетплейсы и средние центры России',author='Исследовательская группа проекта «Расселение России»')
doc.build(story,onFirstPage=footer,onLaterPages=footer)
print(pdf)
