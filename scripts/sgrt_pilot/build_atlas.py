#!/usr/bin/env python3
"""Collect exported pilot PNG figures into a portable PDF, without editing them."""
import argparse
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages


def build(maps, output):
    paths = sorted(maps.rglob('*.png'))
    # Main sweeps already contain these two regions; retain northern/industrial
    # reference pages without duplicating the same geography in the atlas.
    paths = [p for p in paths if not ('reference_all_regions' in p.parts and
             p.name.startswith(('ленинградская_', 'удмуртская_')))]
    if not paths:
        raise ValueError('No exported PNG figures found')
    with PdfPages(output) as pdf:
        for path in paths:
            pixels = plt.imread(path)
            height, width = pixels.shape[:2]
            fig = plt.figure(figsize=(12, 12 * height / width))
            ax = fig.add_axes([0, 0, 1, 1])
            ax.imshow(pixels)
            ax.axis('off')
            pdf.savefig(fig, dpi=180)
            plt.close(fig)
    print(f'{len(paths)} figures -> {output}')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--maps', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    build(a.maps, a.output)
