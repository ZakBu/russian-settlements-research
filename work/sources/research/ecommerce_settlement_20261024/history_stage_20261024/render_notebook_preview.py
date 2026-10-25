"""Read-only local HTML preview of the saved executed notebook; no remote runtime."""
from pathlib import Path
import html
import nbformat
import sys

OUT=Path(__file__).resolve().parent
p=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else OUT/'history_research.ipynb'
n=nbformat.read(p,as_version=4)
title=html.escape(n.cells[0].source.splitlines()[0].lstrip('#').strip())
parts=['<!doctype html><meta charset="utf-8"><title>'+title+'</title>',
       '<style>body{font:17px/1.5 system-ui;margin:32px auto;max-width:1200px;padding:0 24px;color:#222}'
       'section{margin:30px 0;overflow:auto}pre{white-space:pre-wrap}code{font:13px monospace}'
       'table{border-collapse:collapse;font-size:13px}th,td{padding:7px;border:1px solid #ddd}'
       'img{width:100%;height:auto}details{background:#f5f5f5;padding:8px}</style>']
for c in n.cells:
    parts.append('<section>')
    if c.cell_type=='markdown':
        for paragraph in c.source.split('\n\n'):
            if paragraph.startswith('#'):
                first,*rest=paragraph.split('\n',1)
                level=min(3,len(first)-len(first.lstrip('#')))
                text=html.escape(first.lstrip('#').strip())
                parts.append(f'<h{level}>{text}</h{level}>')
                if rest:
                    parts.append('<p>'+html.escape(rest[0]).replace('\n',' ')+'</p>')
            else:
                parts.append('<p>'+html.escape(paragraph).replace('\n',' ')+'</p>')
    else:
        parts.append('<details><summary>Код вычисления</summary><pre><code>'+
                     html.escape(c.source)+'</code></pre></details>')
        for o in c.outputs:
            data=o.get('data',{})
            if 'image/png' in data:
                parts.append('<img alt="График исполненного ноутбука" src="data:image/png;base64,'+
                             data['image/png']+'">')
            elif 'text/html' in data:
                parts.append(data['text/html'])
            elif o.output_type=='stream':
                parts.append('<pre>'+html.escape(o.text)+'</pre>')
            elif 'text/plain' in data:
                parts.append('<pre>'+html.escape(data['text/plain'])+'</pre>')
    parts.append('</section>')
p.with_suffix('.html').write_text('\n'.join(parts))
print(p.with_suffix('.html'))
