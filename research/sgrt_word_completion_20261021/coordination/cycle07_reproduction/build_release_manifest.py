"""Freeze explicitly selected current research files. Does not run or modify science."""
from pathlib import Path
import argparse, hashlib, json

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', type=Path, required=True)
    ap.add_argument('--inventory', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    root = args.root.resolve()
    inventory = json.loads(args.inventory.read_text())
    assert not args.output.exists(), 'Never overwrite a frozen release manifest'
    paths = set()
    for name in inventory['include']:
        relative = Path(name)
        assert not relative.is_absolute() and '..' not in relative.parts
        p = root / relative
        assert p.exists(), name
        for f in ([p] if p.is_file() else p.rglob('*')):
            if f.is_file() and '__pycache__' not in f.parts:
                paths.add(f)
    excluded = set(inventory.get('exclude', []))
    rows = []
    for p in sorted(paths):
        relative = str(p.relative_to(root))
        if relative in excluded or p.resolve() == args.output.resolve():
            continue
        with p.open('rb') as handle:
            h = hashlib.file_digest(handle, 'sha256').hexdigest()
        rows.append({'path': relative, 'bytes': p.stat().st_size, 'sha256': h})
    result = {'schema': 'sgrt.saved_release_bytes.v1',
              'scope': 'Current preliminary computational research; byte inventory is not an additional scientific validation. Raw external downloads are identified by source receipts and may require separate retrieval.',
              'self_reference_policy': 'Manifest, verification receipt and final stakeholder verdict are excluded to avoid recursive hashes; Git records them together.',
              'inventory': str(args.inventory.relative_to(root)), 'files': rows}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'files': len(rows), 'bytes': sum(r['bytes'] for r in rows)}))

if __name__ == '__main__':
    main()
