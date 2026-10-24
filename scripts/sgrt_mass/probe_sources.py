#!/usr/bin/env python3
"""Bounded read-only checks of missing official Chelyabinsk source endpoints."""
import concurrent.futures
import html
import json
import re
import urllib.parse
import urllib.request

URLS=['https://foms74.ru/','http://foms74.ru/','https://www.foms74.ru/',
      'https://argcrb74.ru/fap-i-ambulatoriy/','https://crbsosn74.ru/ru/']


def probe(url):
    try:
        request=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
        with urllib.request.urlopen(request,timeout=15) as response:
            data=response.read(3*1024*1024);final=response.url
            text=data.decode('utf-8',errors='replace')
            links=[urllib.parse.urljoin(final,html.unescape(x)) for x in re.findall(r'href\s*=\s*[\"\x27]([^\"\x27]+)',text,re.I)]
            return {'url':url,'status':response.status,'final_url':final,'bytes':len(data),
                    'registry_or_structure_links':[x for x in links if re.search(r'reestr|реестр|strukt|struct|\.xlsx?|\.zip|fap|амбул',x,re.I)][:70]}
    except Exception as error:return {'url':url,'error':str(error)}


if __name__=='__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        for result in pool.map(probe,URLS):print(json.dumps(result,ensure_ascii=False),flush=True)
