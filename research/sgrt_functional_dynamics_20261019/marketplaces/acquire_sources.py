"""Read-only public-source acquisition. No cookies, impersonation or challenge solving."""
from pathlib import Path
import datetime, hashlib, json, subprocess

ROOT=Path(__file__).resolve().parent
SOURCES={
 'wb_all_points_v11.json':'https://static-basket-01.wbbasket.ru/vol0/data/all-poo-fr-v11.json',
 'hse_pvz_20250419.pdf':'https://www.hse.ru/data/2025/05/01/2005892985/%D0%A1%D0%B5%D0%BC%D0%B8%D0%BD%D0%B0%D1%80%206-%D0%9F%D0%92%D0%97.pdf',
 'pickpoint_february_2021.pdf':'https://pickpoint.ru/files/files/%D0%B3%D1%80%D0%B0%D1%84%D0%B8%D0%BA%20%D1%80%D0%B0%D0%B1%D0%BE%D1%82%D1%8B%20%D0%9F%D0%92%D0%97%20PickPoint_%D1%84%D0%B5%D0%B2%D1%80%D0%B0%D0%BB%D1%8C%202021.pdf',
}
def main():
    out=ROOT/'download_refresh';out.mkdir(exist_ok=True)
    log=[]
    for name,url in SOURCES.items():
        p=out/name
        r=subprocess.run(['curl','--fail','-L','--max-time','45','-D',str(out/(name+'.headers')),'-o',str(p),'-w','%{http_code}',url],capture_output=True)
        log.append(dict(url=url,downloaded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
          path=str(p),returncode=r.returncode,status=r.stdout.decode(),bytes=p.stat().st_size if p.exists()else None,
          sha256=hashlib.sha256(p.read_bytes()).hexdigest()if p.exists()else None))
    (out/'MANIFEST.json').write_text(json.dumps(log,ensure_ascii=False,indent=2))
    print(json.dumps(log,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
