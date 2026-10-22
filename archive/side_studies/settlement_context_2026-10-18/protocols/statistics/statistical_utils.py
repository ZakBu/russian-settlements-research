"""Protocol v1 utilities. No input/outcome reading at import time."""
import hashlib
import numpy as np


def stable_hash(prefix, key):
    return int(hashlib.sha256((prefix + key).encode('utf-8')).hexdigest(), 16)


def split_blocks(lon, lat):
    """Requires pyproj; rejects rather than silently relocating invalid coordinates."""
    from pyproj import Transformer
    lon, lat = np.asarray(lon, float), np.asarray(lat, float)
    if not np.all(np.isfinite(lon) & np.isfinite(lat) & (lat >= -85) & (lat <= 85)
                  & (lon >= -180) & (lon <= 180)):
        raise ValueError('Invalid coordinates or outside EPSG:6933 supported latitude')
    x, y = Transformer.from_crs(4326, 6933, always_xy=True).transform(lon, lat)
    ids = np.array([f'{int(a)}:{int(b)}' for a, b in zip(np.floor(np.asarray(x)/200000),
                                                     np.floor(np.asarray(y)/200000))])
    unique = sorted(set(ids))
    h = {k: stable_hash('settlement-context-v1|', k) % 5 == 0 for k in unique}
    f = {k: stable_hash('settlement-context-fold-v1|', k) % 5 for k in unique}
    return ids, np.array([h[k] for k in ids]), np.array([f[k] for k in ids])


def buffered_train_mask(lat, lon, train_mask, test_mask, buffer_km=60):
    """Drop training centers within radius of any validation center; outcomes unused."""
    from sklearn.neighbors import BallTree
    xy = np.radians(np.column_stack([lat, lon]))
    train_idx, test_idx = np.flatnonzero(train_mask), np.flatnonzero(test_mask)
    result = np.asarray(train_mask, bool).copy()
    if not len(test_idx):
        raise ValueError('Empty test fold')
    if len(train_idx):
        distance, _ = BallTree(xy[test_idx], metric='haversine').query(xy[train_idx], k=1)
        result[train_idx[distance[:, 0] * 6371.0088 < buffer_km]] = False
    return result


def paired_block_bootstrap(block_ids, baseline_loss, augmented_loss, seed=20261018, n_boot=1999):
    """Positive delta means improvement. CI conditions on the supplied trained predictions."""
    block_ids = np.asarray(block_ids)
    base, aug = np.asarray(baseline_loss, float), np.asarray(augmented_loss, float)
    if not (len(block_ids) == len(base) == len(aug)) or not len(base):
        raise ValueError('Mismatched or empty evaluation arrays')
    if not np.all(np.isfinite(base) & np.isfinite(aug)):
        raise ValueError('Invalid losses; exclusions must be explicit upstream')
    blocks, inverse = np.unique(block_ids, return_inverse=True)
    counts = np.bincount(inverse)
    sums = np.bincount(inverse, weights=base-aug)
    rng = np.random.default_rng(seed)
    values = np.empty(n_boot)
    for i in range(n_boot):
        draw = rng.integers(0, len(blocks), size=len(blocks))
        values[i] = sums[draw].sum() / counts[draw].sum()
    return {'delta': float(np.mean(base-aug)), 'ci95': np.quantile(values, [.025, .975]).tolist(),
            'n_rows': len(base), 'n_blocks': len(blocks), 'seed': seed, 'replicates': n_boot,
            'conditional_on_fit': True, 'few_blocks_warning': len(blocks)<30}
