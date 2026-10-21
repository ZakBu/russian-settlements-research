"""Render a manifest-bound cycle06 family; retain overlapping/unknown type hypotheses."""
from pathlib import Path
import argparse
import hashlib
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.collections import LineCollection
from pyproj import Transformer

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TRANSFORM = Transformer.from_crs('EPSG:4326','+proj=aea +lat_1=50 +lat_2=70 +lat_0=60 +lon_0=100 +datum=WGS84 +units=m +no_defs',always_xy=True)
COLORS = plt.get_cmap('tab10')

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(2**20),b''):h.update(b)
    return h.hexdigest()

def run(model, canonical, output):
    if (output/'map_manifest.json').exists():raise FileExistsError('Use a fresh atlas output directory')
    output.mkdir(parents=True,exist_ok=True)
    frozen=json.loads((model/'output_manifest.json').read_text())
    config_path=Path(frozen['configuration_path'])
    if not config_path.is_absolute():config_path=ROOT.parent.parent/config_path
    if sha(config_path)!=frozen['configuration_sha256']:raise ValueError('Configuration differs from frozen manifest')
    config=json.loads(config_path.read_text())
    network_year=config.get('transport_reference_year','не указан')
    sources=[model/n for n in ['nodes.parquet','memberships.parquet','systems.parquet','candidate_centers.parquet','network_accessibility.parquet','output_manifest.json']]
    sources += [canonical/'word_type_hypotheses.parquet',canonical/'manifest.json',Path(__file__)]
    sources.append(config_path)
    for p in sources:
        if p.parent.resolve()==model.resolve() and p.name in frozen['files'] and sha(p)!=frozen['files'][p.name]['sha256']:raise ValueError('Model derivative differs from frozen manifest: '+str(p))
    canonical_manifest=json.loads((canonical/'manifest.json').read_text())
    if canonical_manifest.get('model_output_manifest_sha256')!=sha(model/'output_manifest.json'):raise ValueError('Canonical types belong to a different model')
    canonical_file=canonical_manifest.get('files',{}).get('word_type_hypotheses.parquet',{})
    if canonical_file and sha(canonical/'word_type_hypotheses.parquet')!=canonical_file['sha256']:raise ValueError('Canonical types differ from manifest')
    hashes={str(p.resolve()):sha(p) for p in sources}
    nodes=pd.read_parquet(model/'nodes.parquet'); members=pd.read_parquet(model/'memberships.parquet')
    systems=pd.read_parquet(model/'systems.parquet'); centers=pd.read_parquet(model/'candidate_centers.parquet')
    types=pd.read_parquet(canonical/'word_type_hypotheses.parquet')
    xy=nodes[['id','lon','lat','_population_axis_row']].copy()
    xy['x'],xy['y']=TRANSFORM.transform(xy.lon.to_numpy(float),xy.lat.to_numpy(float))
    good=np.isfinite(xy[['x','y']].to_numpy(float)).all(axis=1)
    bounds=np.nanquantile(xy.loc[good,['x','y']],[0,1],axis=0)
    population=xy.loc[good & xy._population_axis_row.fillna(False)]
    m=members.merge(xy[['id','x','y']],on='id',validate='one_to_one')
    s=systems.drop(columns=['lat','lon'],errors='ignore').merge(xy[['id','x','y']].rename(columns={'id':'center_id'}),on='center_id',validate='many_to_one')
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'pdf.fonttype':42,'svg.fonttype':'none'})
    rows=[]
    def base(ax,title):
        ax.scatter(population.x,population.y,s=.12,color='#d3d8da',rasterized=True,linewidths=0)
        ax.set(xlim=(bounds[0,0]-1e5,bounds[1,0]+1e5),ylim=(bounds[0,1]-1e5,bounds[1,1]+1e5),aspect='equal')
        ax.set_xticks([]);ax.set_yticks([]);ax.set_title(title,loc='left',fontsize=14)
        for spine in ax.spines.values():spine.set_visible(False)
    with PdfPages(output/'SGRT_CYCLE06_MODEL_ATLAS.pdf') as atlas:
        def save(fig,name,caption,stats):
            fig.text(.04,.025,caption,fontsize=8,va='bottom')
            files=[]
            for ext in ['png','pdf','svg']:
                p=output/(name+'.'+ext);fig.savefig(p,dpi=180,bbox_inches='tight');files.append({'path':p.name,'sha256':sha(p),'bytes':p.stat().st_size})
            atlas.savefig(fig,bbox_inches='tight');plt.close(fig)
            rows.append({'figure':name,'statistics':stats,'outputs':files})
        fig,ax=plt.subplots(figsize=(16,8));base(ax,'Потенциальные центры и эмпирические порядки')
        c=centers.merge(xy[['id','x','y']],on='id',validate='one_to_one')
        for rank,g in c.groupby('intrinsic_empirical_rank'):
            ax.scatter(g.x,g.y,s=4+5*int(rank),color=COLORS(int(rank)-1),label=f'Порядок {int(rank)}: {len(g)}',linewidths=.2,edgecolors='white',rasterized=True)
        ax.legend(loc='lower left')
        save(fig,'01_centers','Порядки определены статистической моделью Ci; это не доказанная иерархия услуг.\nМасса Mi рассчитана по собственным показателям, без подгонки к населению полученной зоны.',{'centers':len(c),'ranks':c.intrinsic_empirical_rank.value_counts().sort_index().to_dict()})
        levels=sorted(s.level.unique())
        for level in levels:
            col=f'center_id_l{level}';d=m[m[col].notna() & m._population_axis_row.fillna(False)].copy()
            # Deterministic IDs supply a display color, not a further class.
            d['color']=d[col].map(lambda value:int(hashlib.sha256(str(value).encode()).hexdigest()[:8],16)%20)
            fig,ax=plt.subplots(figsize=(16,8));base(ax,f'СГРТ: уровень {level}')
            ax.scatter(d.x,d.y,c=d.color,cmap='tab20',vmin=0,vmax=19,s=.65,linewidths=0,rasterized=True)
            ctr=s[s.level.eq(level)];ax.scatter(ctr.x,ctr.y,s=5,c='black',marker='+',linewidths=.4,rasterized=True)
            save(fig,f'02_membership_level{level}',f'{len(d):,} аддитивных единиц в {len(ctr):,} системах; серый фон — вне назначения на этом уровне.\nПоказана принадлежность точек НП. Дорожная сеть {network_year}: сценарий доступности, не наблюдаемые поездки.'.replace(',',' '),{'level':int(level),'systems':len(ctr),'assigned_population_units':len(d)})
            t=types[types.level.eq(level)&types.operational_hypothesis].merge(xy[['id','x','y']].rename(columns={'id':'center_id'}),on='center_id',validate='many_to_one')
            fig,axs=plt.subplots(3,3,figsize=(17,9));fig.suptitle(f'Девять типов Word: проверяемые гипотезы, уровень {level}',fontsize=17)
            for typ,ax in enumerate(axs.flat,1):
                g=t[t.word_type.eq(typ)];base(ax,f'Тип {typ}: {len(g)}')
                ax.scatter(g.x,g.y,s=12,color=COLORS(typ-1),edgecolors='white',linewidths=.3,rasterized=True)
            fig.subplots_adjust(bottom=.10,hspace=.22)
            save(fig,f'03_word_types_level{level}','Панели допускают несколько гипотез для одной системы. Пустая панель означает отсутствие принятой предварительной комбинации индикаторов.\nНеизвестные механизмы и пропущенные данные не заменены отсутствием; гипотеза не равна доказанному механизму.',{'level':int(level),'candidate_center_type_pairs':len(t),'by_type':t.word_type.value_counts().sort_index().to_dict()})
            q=types[types.level.eq(level)].drop_duplicates(['level','center_id'])
            q=q[q.population_pair_complete & np.isfinite(q.center_annual_rate)&np.isfinite(q.rural_annual_rate)]
            fig,ax=plt.subplots(figsize=(10,8));ax.scatter(q.center_annual_rate*100,q.rural_annual_rate*100,s=9,alpha=.5)
            ax.axhline(0,color='#777777',lw=.7);ax.axvline(0,color='#777777',lw=.7)
            ax.set(xlabel='Центр: среднегодовое изменение населения, %',ylabel='Сельское окружение: среднегодовое изменение, %',title=f'Динамика центра и окружения, 2010–2021, уровень {level}')
            ax.grid(alpha=.15)
            save(fig,f'04_dynamics_level{level}','Только численно полные пары; полнота чисел не доказывает неизменность исторических границ.\nСельская статистическая категория задана отдельным источником, а не названием типа НП.',{'level':int(level),'numeric_complete_pairs':len(q),'all_systems':int(s.level.eq(level).sum())})
        n=nodes.merge(xy[['id','x','y']],on='id',validate='one_to_one').merge(pd.read_parquet(model/'network_accessibility.parquet'),on='id',validate='one_to_one')
        fig,ax=plt.subplots(figsize=(16,8));base(ax,'Доступность крупных городов и двух федеральных городских контекстов')
        column='nearest_large_city_network_minutes';q=n[n[column].notna() & n._population_axis_row.fillna(False)]
        dots=ax.scatter(q.x,q.y,c=q[column],s=.7,cmap='viridis',vmin=0,vmax=360,rasterized=True,linewidths=0)
        fig.colorbar(dots,ax=ax,shrink=.7,label='Минуты по сценарию дорожной доступности')
        save(fig,'05_large_city_access','Порог собственного населения городов — 100 тысяч; Москва и Санкт-Петербург — отдельные контексты городов-субъектов.\nПри отсутствии рассчитанного пути значение неизвестно: оно не превращено в периферийный тип.',{'population_units_with_path':len(q),'population_threshold':100000})
    changed=[p for p,h in hashes.items() if sha(Path(p))!=h]
    if changed:raise RuntimeError('Inputs changed while rendering: '+repr(changed))
    receipt={'status':'COMPUTED_PENDING_INDEPENDENT_VISUAL_AND_SOURCE_REVIEW','model_output':str(model),'canonical_output':str(canonical),'input_sha256':hashes,'figures':rows,'atlas':{'sha256':sha(output/'SGRT_CYCLE06_MODEL_ATLAS.pdf'),'pages':len(rows)},'all_inputs_unchanged':not changed,'transport_reference_year':network_year,'geometry':'actual NP point memberships; no invented polygon borders'}
    (output/'map_manifest.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'figures':len(rows),'atlas_pages':len(rows),'output':str(output)},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--model-output',type=Path,required=True);p.add_argument('--canonical-output',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.model_output,a.canonical_output,a.output)
