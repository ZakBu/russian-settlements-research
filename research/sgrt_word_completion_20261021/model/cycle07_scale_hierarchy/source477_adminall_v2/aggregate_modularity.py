"""Constrained weighted Newman-Girvan OBJECTIVE, own agglomerative algorithm.
Fixed original degrees; aggregate affinities updated after every merge.
Not the original edge-betweenness algorithm, not observed-flow delimitation.
"""
import heapq,math

def agglomerate(initial_units, edges, envelope, gamma=1., minimum_gain=0., initial_original_degrees=None, initial_internal_unordered_weight=None):
    """edges iterable(left,right,nonnegativeweight,witness_id), undirected ONCE.
    envelope(unit_a,unit_b) -> (merged_unit_or_None, source_witness_dict).
    Every accepted step improves Q on the ORIGINAL fixed weighted graph.
    Returns units, accepted-event dendrogram, rejection counters.
    """
    if not math.isfinite(gamma) or gamma<=0:raise ValueError('invalid gamma')
    if not math.isfinite(minimum_gain) or minimum_gain<0:raise ValueError('invalid gain')
    units={u.key:u for u in initial_units}
    if len(units)!=len(initial_units):raise ValueError('duplicate unit key')
    adj={k:{} for k in units};degree={k:0. for k in units};edge_witness={}
    for a,b,w,witness in edges:
        if a not in units or b not in units or a==b:raise ValueError('invalid atomic edge endpoint')
        if not math.isfinite(w) or w<0 or not witness:raise ValueError('invalid source affinity')
        if w==0:continue
        pair=tuple(sorted((a,b)))
        if pair in edge_witness:raise ValueError('duplicate undirected atomic edge')
        edge_witness[pair]=witness
        adj[a][b]=w;adj[b][a]=w;degree[a]+=w;degree[b]+=w
    internal=initial_internal_unordered_weight or {k:0. for k in units}
    if set(internal)!=set(units) or any(not math.isfinite(v) or v<0 for v in internal.values()):raise ValueError('invalid initial internal affinities')
    if initial_original_degrees is not None:
        if set(initial_original_degrees)!=set(units):raise ValueError('original-degree key mismatch')
        for k,v in initial_original_degrees.items():
            if not math.isfinite(v) or v<0 or not math.isclose(v,degree[k]+2*internal[k],rel_tol=1e-10,abs_tol=1e-12):raise ValueError('original degree inconsistent with initial cross/internal graph')
        degree=dict(initial_original_degrees)
    elif any(internal.values()):raise ValueError('initial aggregate units require original degrees')
    total=sum(degree.values())
    if not total:return list(units.values()),[],dict(no_positive_source_edges=1)
    # For initial single provider cores e_ii=0; initial Q accounts degree null.
    q=sum(2*internal[k]/total-gamma*(degree[k]/total)**2 for k in units)
    initial_q=q;heap=[];serial=0
    def push(a,b):
        nonlocal serial
        a,b=sorted((a,b));w=adj[a].get(b,0.)
        gain=2*w/total-2*gamma*degree[a]*degree[b]/total**2
        if gain>minimum_gain:
            serial+=1;heapq.heappush(heap,(-gain,a,b,serial,w))
    for a in adj:
        for b in adj[a]:
            if a<b:push(a,b)
    events=[];rejections=dict(envelope_rejected=0,stale_heap_entries=0,nonpositive_gain=0)
    while heap:
        neg,a,b,_,oldw=heapq.heappop(heap)
        if a not in units or b not in units:
            rejections['stale_heap_entries']+=1;continue
        w=adj[a].get(b,0.)
        actual=2*w/total-2*gamma*degree[a]*degree[b]/total**2
        if w!=oldw or abs(actual+neg)>1e-12:raise AssertionError('live score changed without new node')
        if actual<=minimum_gain:rejections['nonpositive_gain']+=1;continue
        merged,witness=envelope(units[a],units[b])
        if merged is None:rejections['envelope_rejected']+=1;continue
        new=merged.key
        if new in units:raise ValueError('merged unit key collision')
        # Sum EVERY original crossedge, retaining fixed-original degree totals.
        neighbors=(set(adj[a])|set(adj[b]))-{a,b}
        newadj={x:math.fsum((adj[a].get(x,0.),adj[b].get(x,0.))) for x in neighbors}
        ka,kb=degree[a],degree[b];degree[new]=math.fsum((ka,kb))
        for x in neighbors:
            adj[x].pop(a,None);adj[x].pop(b,None);adj[x][new]=newadj[x]
        for old in [a,b]:adj.pop(old);units.pop(old);degree.pop(old)
        adj[new]=newadj;units[new]=merged;q+=actual
        events.append(dict(merge_index=len(events)+1,left=a,right=b,parent=new,cross_affinity=w,left_original_degree=ka,right_original_degree=kb,total_original_degree=total,gamma=gamma,delta_q=actual,q=q,initial_q=initial_q,source_envelope_witness=witness))
        for x in neighbors:push(new,x)
        # Bound lazy queue memory; this changes no live scores or tie policy.
        if len(heap)>4*max(1,sum(map(len,adj.values()))):
            heap=[]
            for x in adj:
                for y in adj[x]:
                    if x<y:push(x,y)
    return list(units.values()),events,rejections
