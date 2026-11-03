"""Restore the fully read primary paper; never include it in public outputs."""
from pathlib import Path
import hashlib,urllib.request
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'work/ecommerce_operations_20261104/kuksin2026.pdf'
PIN='1a77c7f74d972be57d53c8e62d7f89764290be3cb87308c9614e48448ce4d558'
def main():
    OUT.parent.mkdir(parents=True,exist_ok=True)
    if not OUT.exists():
        with urllib.request.urlopen('https://peasantstudies.ru/ru/category/62-2026-11-3?download=789',timeout=60)as r:body=r.read()
        assert hashlib.sha256(body).hexdigest()==PIN
        OUT.write_bytes(body)
    assert hashlib.sha256(OUT.read_bytes()).hexdigest()==PIN
    print('Full primary paper restored; pinned SHA256 matches. Not redistributed.')
if __name__=='__main__':main()
