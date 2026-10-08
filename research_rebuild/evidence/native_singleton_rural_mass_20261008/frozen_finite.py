import numpy as np
def finite(state):
    """Vector check on all component members, including nonordinary members."""
    obs = state.obs
    bad = ~obs.source_record_id.isin(state.point_rows) | ~np.isfinite(obs.population)
    bad_roots = set(obs.loc[bad, 'root'])
    bad_roots.update(state.uf.find(key) for key in state.conflicting_point_targets)
    ordinary = obs.is_additive_settlement_record.fillna(False)
    ordinary &= ~obs.region_norm.isin(['москва', 'санкт петербург', 'севастополь'])
    ordinary &= ~(obs.census_year.eq(2021) & obs.region_norm.eq('крым'))
    data = obs[ordinary]
    roots = {root for root in set(data.root)
             if state.years[root] == {2002, 2010, 2021} and root not in bad_roots}
    full = data[data.root.isin(roots)]
    return {'histories': len(roots), 'populations_by_year': {
        str(int(year)): int(group.population.sum()) for year, group in full.groupby('census_year')}}

