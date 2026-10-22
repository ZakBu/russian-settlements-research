#!/usr/bin/env python3
"""Append a structured research event and detailed Markdown diary entry."""
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import json


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--entry',type=Path,required=True,help='JSON with topic, goal, inputs, decisions, commands, outputs, checks, limitations, next_steps')
    p.add_argument('--root',type=Path,default=Path('.'))
    a=p.parse_args();record=json.loads(a.entry.read_text())
    required=['topic','goal','inputs','decisions','commands','outputs','checks','limitations','next_steps']
    missing=[k for k in required if k not in record]
    if missing:p.error('Missing required fields: '+', '.join(missing))
    now=datetime.now(ZoneInfo('Europe/Moscow'));record['time_moscow']=now.isoformat()
    directory=a.root/'research_context/diary';directory.mkdir(parents=True,exist_ok=True)
    with open(directory/(now.date().isoformat()+'.md'),'a') as f:
        f.write('\n## '+record['time_moscow']+' — '+record['topic']+'\n\n')
        for name in required[1:]:
            f.write('### '+name+'\n\n')
            value=record[name]
            if isinstance(value,str):f.write(value+'\n\n')
            else:f.write('```json\n'+json.dumps(value,ensure_ascii=False,indent=2)+'\n```\n\n')
    with open(directory/'events.jsonl','a') as f:f.write(json.dumps(record,ensure_ascii=False)+'\n')
    print(record['time_moscow'])


if __name__=='__main__':main()
