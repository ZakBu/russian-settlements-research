"""Readable A4 reports with full-size vector map appendices in the science PDF."""
from pathlib import Path
import re,html,json,hashlib,textwrap
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,KeepTogether,Preformatted
from reportlab.lib.pagesizes import A4
from matplotlib.font_manager import findfont,FontProperties
from pypdf import PdfReader,PdfWriter

R=Path(__file__).resolve().parent

def create(source,name,brief=False):
    out=R/'output/pdf';out.mkdir(parents=True,exist_ok=True)
    for n,w in [('DV','normal'),('DVB','bold')]:pdfmetrics.registerFont(TTFont(n,findfont(FontProperties(family='DejaVu Sans',weight=w))))
    pdfmetrics.registerFontFamily('DV',normal='DV',bold='DVB',italic='DV',boldItalic='DVB')
    pdfmetrics.registerFont(TTFont('DVM',findfont(FontProperties(family='DejaVu Sans Mono'))))
    style=ParagraphStyle('body',fontName='DV',fontSize=10 if brief else 9.3,leading=14 if brief else 13.5,spaceAfter=7,textColor=colors.HexColor('#20384a'))
    hs={1:ParagraphStyle('title',parent=style,fontName='DVB',fontSize=18,leading=22,spaceAfter=13,keepWithNext=True),2:ParagraphStyle('section',parent=style,fontName='DVB',fontSize=12.5,leading=17,spaceBefore=11,spaceAfter=8,keepWithNext=True),3:ParagraphStyle('sub',parent=style,fontName='DVB',fontSize=10.5,leading=14,spaceBefore=8,keepWithNext=True)}
    cell=ParagraphStyle('cell',parent=style,fontSize=7.5,leading=10.5,spaceAfter=0)
    code_style=ParagraphStyle('code',parent=style,fontName='DVM',fontSize=7,leading=10,spaceBefore=4,spaceAfter=9,backColor=colors.HexColor('#f0f5f8'),borderPadding=6)
    def inline(s):
        s=html.escape(s);s=re.sub(r'\*\*(.*?)\*\*',r'<b>\1</b>',s)
        s=re.sub(r'`([^`]+)`',r'<font color="#286f97">\1</font>',s)
        return re.sub(r'\[([^\]]+)\]\(([^)]+)\)',r'\1',s)
    lines=source.read_text().splitlines();story=[];i=0;mapno=0
    while i<len(lines):
        s=lines[i].strip()
        if not s:i+=1;continue
        if s.startswith('```'):
            block=[];i+=1
            while i<len(lines) and not lines[i].strip().startswith('```'):
                pieces=textwrap.wrap(lines[i],width=96,break_long_words=False,break_on_hyphens=False) or ['']
                block.append((' \\\n  ').join(pieces));i+=1
            i+=1
            story.extend([Preformatted('\n'.join(block),code_style),Spacer(1,5)]);continue
        if s.startswith('!['):
            mapno+=1;label=re.match(r'!\[([^\]]+)\]',s).group(1)
            story.append(Paragraph('Иллюстрация '+str(mapno)+'. '+inline(label)+'. Полноразмерный лист приведён в приложении.',style));i+=1;continue
        if s.startswith('|'):
            rows=[]
            while i<len(lines) and lines[i].strip().startswith('|'):
                a=lines[i].strip().strip('|').split('|');i+=1
                if all(re.fullmatch(r'[\s:\-]+',v) for v in a):continue
                rows.append([Paragraph(inline(v.strip()),cell) for v in a])
            width=A4[0]-82
            widths=[width/len(rows[0])]*len(rows[0])
            if len(rows[0])==5:widths=[width*.25,width*.12,width*.12,width*.12,width*.39]
            t=Table(rows,colWidths=widths,repeatRows=1,hAlign='LEFT')
            t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#d9e8f0')),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f0f5f8')]),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]));story.extend([KeepTogether(t) if len(rows)<9 else t,Spacer(1,10)]);continue
        if s.startswith('#'):
            level=min(len(s)-len(s.lstrip('#')),3);story.append(Paragraph(inline(s.lstrip('#').strip()),hs[level]));i+=1;continue
        buf=[s];i+=1
        while i<len(lines) and lines[i].strip() and not lines[i].strip().startswith(('#','|','![')):
            buf.append(lines[i].strip());i+=1
        story.append(Paragraph(inline(' '.join(buf)),style))
    def footer(c,d):
        c.setStrokeColor(colors.HexColor('#b0c5d2'));c.line(41,34,A4[0]-41,34);c.setFont('DV',7);c.setFillColor(colors.HexColor('#536e80'));c.drawString(41,23,'СГРТ: общероссийская интеграция данных | 19.10.2026');c.drawRightString(A4[0]-41,23,str(d.page))
    temp=out/(name+'.body.pdf');dest=out/name
    SimpleDocTemplate(str(temp),pagesize=A4,rightMargin=41,leftMargin=41,topMargin=36,bottomMargin=45,title='Функции поселений России: национальная интеграция',author='Исследовательский проект Захара Бучинцева').build(story,onFirstPage=footer,onLaterPages=footer)
    w=PdfWriter();w.append(str(temp));textpages=len(w.pages)
    if not brief:
        for f in ['figures/01_function_profiles.pdf','figures/02_source_agreement.pdf','figures/03_evidence_gaps.pdf']:w.append(str(R/f))
    w.add_metadata({'/Title':'Опорность: результаты исследования' if brief else 'Функции поселений России: национальная интеграция','/Author':'Исследовательский проект Захара Бучинцева'})
    with dest.open('wb') as f:w.write(f)
    assert len(PdfReader(dest).pages)==len(w.pages)
    return dict(file=str(dest.relative_to(R)),source=str(source.relative_to(R)),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),bytes=dest.stat().st_size,text_pages=textpages,map_pages=len(w.pages)-textpages,pages=len(w.pages))

if __name__=='__main__':
    records=[create(R/'NATIONAL_RESULTS.md','SGRT_NATIONAL_FUNCTIONS_REPORT.pdf'),create(R/'COMMUNICATION.md','SGRT_NATIONAL_FUNCTIONS_BRIEF.pdf',True)]
    (R/'output/pdf/MANIFEST.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n');print(json.dumps(records,ensure_ascii=False))
