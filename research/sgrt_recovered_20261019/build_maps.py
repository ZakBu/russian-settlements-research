"""Data-backed national maps, equal-area projection, three regional enlargements."""
from pathlib import Path
import argparse, hashlib, json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from pyproj import Transformer
from PIL import Image
from pypdf import PdfReader, PdfWriter

ROOT=Path(__file__).resolve().parent
P=argparse.ArgumentParser();P.add_argument('--out',type=Path,default=ROOT/'maps');P.add_argument('--background',type=Path,default=ROOT.parents[2]/'recovery_inputs/enrichment/world.geojson');P.add_argument('--only-functional',action='store_true');P.add_argument('--only-map',default=None);args=P.parse_args()
OUT=args.out;OUT.mkdir(parents=True,exist_ok=True)
if not args.background.exists(): args.background=ROOT.parents[3]/'recovery_inputs/enrichment/world.geojson'
T=Transformer.from_crs('EPSG:4326','+proj=aea +lat_1=50 +lat_2=70 +lat_0=60 +lon_0=100 +datum=WGS84 +units=m',always_xy=True)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'pdf.fonttype':42,'svg.fonttype':'none'})
mem=pd.read_parquet(ROOT/'model/nearest_membership.parquet')
cent=pd.read_parquet(ROOT/'model/centers.parquet')
zones=pd.read_parquet(ROOT/'model/zone_trajectories.parquet').set_index('center_id')
panel=pd.read_parquet(ROOT/'data/panel.parquet')
xx,yy=T.transform(mem.lon.to_numpy(),mem.lat.to_numpy())
cx,cy=T.transform(cent.lon.to_numpy(),cent.lat.to_numpy())
features=json.loads(args.background.read_text())['features']
rings=[]
for f in features:
    geom=f['geometry']
    polys=[geom['coordinates']] if geom['type']=='Polygon' else geom['coordinates'] if geom['type']=='MultiPolygon' else []
    for poly in polys:
        a=np.asarray(poly[0]);x,y=T.transform(a[:,0],a[:,1]);rings.append((x,y))
extent=(float(np.nanmin(xx)-180000),float(np.nanmax(xx)+180000),float(np.nanmin(yy)-180000),float(np.nanmax(yy)+180000))
# Include all national background islands/coastline as well as every observed point.
for f in features:
    if f['properties'].get('ADMIN')=='Russia':
        polys=f['geometry']['coordinates'] if f['geometry']['type']=='MultiPolygon' else [f['geometry']['coordinates']]
        a=np.concatenate([np.asarray(poly[0]) for poly in polys]);rx,ry=T.transform(a[:,0],a[:,1])
        extent=(min(extent[0],float(np.min(rx)-50000)),max(extent[1],float(np.max(rx)+50000)),min(extent[2],float(np.min(ry)-50000)),max(extent[3],float(np.max(ry)+50000)))
manifest=[]
def backdrop(ax,extent):
    ax.set_facecolor('#f5f8fb')
    for x,y in rings: ax.fill(x,y,fc='#e9e8e3',ec='#a8b0b5',lw=.28,zorder=0)
    ax.set_xlim(extent[:2]);ax.set_ylim(extent[2:]);ax.set_aspect('equal');ax.set_xticks([]);ax.set_yticks([])
    for s in ax.spines.values():s.set_color('#c1cad1');s.set_linewidth(.6)

def draw(name,title,subtitle,values,colors,labels,pointset='settlements',edges=False,footnote=None):
    if args.only_functional and int(name[:2])<9:return
    if args.only_map and not name.startswith(args.only_map):return
    val=np.asarray(values); x,y=(xx,yy) if pointset=='settlements' else (cx,cy)
    assert len(val)==len(x),(name,len(val),len(x))
    fig=plt.figure(figsize=(24,15),facecolor='white')
    fig.text(.035,.961,title,fontsize=23,weight='bold',color='#102d43')
    fig.text(.035,.932,subtitle,fontsize=11,color='#405768')
    ax=fig.add_axes([.025,.335,.95,.57]);backdrop(ax,extent)
    def points(a,mask=None):
        if mask is None:mask=np.ones(len(val),bool)
        for k,color in colors.items():
            m=mask&(val==k)
            if m.any():a.scatter(x[m],y[m],s=3.5 if pointset=='settlements' else 5.5,c=color,edgecolors='none',alpha=.83,zorder=3,rasterized=True)
    if edges:
        ix=cent.set_index('id')
        for r in cent.itertuples():
            if pd.notna(r.parent_id) and r.parent_id in ix.index:
                q=ix.loc[r.parent_id];a,b=T.transform([r.lon,q.lon],[r.lat,q.lat]);ax.plot(a,b,color='#244f70',lw=.25,alpha=.3,zorder=1)
    points(ax)
    boxes=[('Москва и соседние области',(34,44,53,59)),('Среднее Поволжье',(45,56,51,59)),('Юг Восточной Сибири',(100,112,49,57))]
    for pos,(label,box) in zip([.035,.36,.685],boxes):
        ia=fig.add_axes([pos,.058,.28,.215]);lon0,lon1,lat0,lat1=box
        qx,qy=T.transform([lon0,lon1,lon0,lon1],[lat0,lat0,lat1,lat1]);ex=(min(qx),max(qx),min(qy),max(qy));backdrop(ia,ex)
        mask=(x>=ex[0])&(x<=ex[1])&(y>=ex[2])&(y<=ex[3]);points(ia,mask)
        ia.set_title(label,fontsize=11,loc='left',pad=5,color='#28465c')
    handles=[Line2D([],[],marker='o',linestyle='',color=colors[k],markersize=6,label=labels[k]) for k in colors]
    fig.legend(handles=handles,loc='center',bbox_to_anchor=(.5,.305),ncol=min(5,len(handles)),frameon=False,fontsize=10)
    fig.text(.035,.018,footnote or 'Панель stage71; координаты современного среза. Расчётные зоны не являются доказанными потоками. Базовые массы: 2010. Подложка: Natural Earth 1:50 млн.',fontsize=8.5,color='#52626e')
    for ext in ['png','svg','pdf']:
        p=OUT/(name+'.'+ext);temp=OUT/(name+'.tmp.'+ext)
        fig.savefig(temp,dpi=250,facecolor='white')
        if ext=='pdf':assert len(PdfReader(temp).pages)==1
        elif ext=='png':
            with Image.open(temp) as check:check.verify()
        else:
            import xml.etree.ElementTree as ET
            ET.parse(temp)
        temp.replace(p)
        manifest.append({'file':p.name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'map':name})
    plt.close(fig)

growthcols={0:'#a52339',1:'#dc6c6d',2:'#edb9b3',3:'#e7e5df',4:'#b4cfdf',5:'#5a9cc3',6:'#176ba0',7:'#f4b544',8:'#777b80'}
growthlabels={0:'Убыль ≥50%',1:'Убыль 25–50%',2:'Убыль 5–25%',3:'От −5 до +5%',4:'Рост 5–25%',5:'Рост 25–50%',6:'Рост ≥50%',7:'Нулевая база → население',8:'Оба значения равны нулю'}
def gclass(a,b):
    a=np.asarray(a);b=np.asarray(b);r=np.divide(b-a,a,out=np.full(len(a),np.nan),where=a>0)*100
    c=np.digitize(r,[-50,-25,-5,5,25,50]).astype(int);c[(a==0)&(b>0)]=7;c[(a==0)&(b==0)]=8;return c
draw('01_population_2010_2021','Демографическая динамика населённых пунктов, 2010–2021','Все наблюдаемые значения, включая нули; цвет обозначает изменение численности одного и того же НП.',gclass(mem.population_2010,mem.population_2021),growthcols,growthlabels)
draw('02_population_2002_2021','Демографическая динамика населённых пунктов, 2002–2021','Фиксированная панель из 142 570 населённых пунктов; национальная полнота населения не заявляется.',gclass(mem.population_2002,mem.population_2021),growthcols,growthlabels)
zg=zones.reindex(mem.center_id)
draw('03_fixed_zone_growth','Динамика населения фиксированных низовых районов, 2010–2021','Низовая принадлежность зафиксирована по координатам и центрам 2010; все нижние районы сохраняются внутри иерархии.',gclass(zg.population_2010.fillna(0),zg.population_2021.fillna(0)),growthcols,growthlabels)
typemap={'joint_decline':0,'center_decline_environment_non_decline':1,'joint_non_decline':2,'center_non_decline_environment_decline':3,'environment_zero_to_positive_observed':4,'no_environment':5,'center_outcome_undefined':6}
t=zg.trajectory.fillna('center_outcome_undefined').map(typemap).fillna(6).astype(int)
draw('04_center_environment','Центр и окружение: сочетания демографических траекторий','Неубыль включает равенство. Знак динамики не доказывает миграцию между центром и окружением.',t,{0:'#b5364b',1:'#de9d67',2:'#297baf',3:'#8c63a4',4:'#48a99c',5:'#babfc3',6:'#5d6267'},{0:'Убыль центра и окружения',1:'Убыль центра / неубыль окружения',2:'Неубыль обоих',3:'Неубыль центра / убыль окружения',4:'Окружение: 0 → положительное',5:'Нет населённого окружения',6:'Нет исхода центра'})
margin=mem.raw_huff_probability_margin.fillna(0)
amb=np.digitize(margin,[.1,.25,.5])
draw('05_potential_competition','Конкуренция потенциальных центров, 2010','Разрыв между двумя крупнейшими нормированными весами Хаффа. Этот вес не является вероятностью nearest-принадлежности.',amb,{0:'#b6314b',1:'#e6a171',2:'#a1c7d6',3:'#21678b'},{0:'Разрыв <0,10',1:'0,10–0,25',2:'0,25–0,50',3:'≥0,50'})
depth=np.minimum(cent.depth_to_root,3)
draw('06_nested_hierarchy','Сохранённая вложенность центров и районов','Рёбра ведут к более сильному родителю при внешнем поле выше собственного. Цвет — число шагов до корня; 3 означает ≥3.',depth,{0:'#173b59',1:'#327daa',2:'#76b0c6',3:'#df9c55'},{0:'Самостоятельный корень',1:'Один шаг',2:'Два шага',3:'Три и более'},pointset='centers',edges=True)
distance=np.digitize(mem.distance_km.fillna(1e9),[5,10,20,50,100.001])
draw('07_local_distance','Геодезическое расстояние до низового центра','Сферические километры; транспортный граф, дорожные времена и изохроны этим расчётом не воспроизводятся.',distance,{0:'#173f64',1:'#397fab',2:'#7fb7cc',3:'#e0c67e',4:'#cf7b54',5:'#74797f'},{0:'До 5 км',1:'5–10 км',2:'10–20 км',3:'20–50 км',4:'50–100 км',5:'Не назначено'})
historical=panel.set_index('id').reindex(mem.id)
hc=np.where(historical.population_1989.notna(),np.where(historical.population_1989_primary,2,1),0)
draw('08_partial_1989','Покрытие частичной исторической когорты 1989 года','Только точные однозначные связи. Не является общероссийской переписью; основания численности и границы неоднородны.',hc,{0:'#c6cbce',1:'#e8ad64',2:'#176b9b'},{0:'Нет связанного значения',1:'Вторичный источник',2:'Первичный источник / транскрипция'})

# Optional completed functional layers are included only after successful readback.
crop=ROOT/'agriculture/zone_functional_main.csv'
if crop.exists():
    c=pd.read_csv(crop);s=c.set_index('center_id').functional_context.reindex(mem.center_id).fillna('missing')
    colors={'grain':'#d0a547','technical':'#a99c32','fodder':'#5b9b7f','potato':'#a3789d','vegetables':'#e08058','melon':'#d4a089','mixed':'#6496b3','mosaic':'#434d78','zero_sown':'#ccd0c7','missing':'#c2c6ca'}
    labels={'grain':'Зерновой','technical':'Технические культуры','fodder':'Кормовой','potato':'Картофельный','vegetables':'Овощной','melon':'Бахчевой','mixed':'Смешанный муниципальный','mosaic':'Мозаика разных профилей','zero_sown':'Нулевая посевная площадь','missing':'Недостаточное покрытие'}
    used={k:v for k,v in colors.items() if k in s.unique()}
    draw('09_agricultural_profile','Аграрные профили низовых районов','Композиция муниципальных посевных структур 2021 по числу НП. Покрытие ≥80%, доминирование ≥60%; поля не локализуются.',s,used,labels)
econ=ROOT/'rfsd/primary2010/functional/functional_types.parquet'
if econ.exists():
    e=pd.read_parquet(econ);e=e[(e.year==2021)&(e.max_distance_km==5)&(e.quality=='baseline')&(e.basis=='count')]
    s=e.set_index('center_id').dominant_specialization.reindex(mem.center_id).fillna('unobserved')
    mapping={'A':'A','B':'B','C':'C','G':'G','H':'H','no_qualifying_specialization':'diversified','insufficient_reporters':'few','unobserved':'unobserved'}
    s=s.map(lambda k:mapping.get(k,'other'))
    draw('10_reporting_economic_profile','Отраслевая структура отчётных организаций, 2021','Специализация: доля ≥20%, LQ ≥1,25, не менее 5 организаций. Юридический адрес не равен месту деятельности или рабочим местам.',s,{'A':'#638b52','B':'#96515d','C':'#b68842','G':'#6278ad','H':'#378c9c','other':'#9979aa','diversified':'#4b6579','few':'#c0c4c7','unobserved':'#e1e3e4'},{'A':'Сельское, лесное хозяйство, рыболовство','B':'Добыча','C':'Обрабатывающая промышленность','G':'Торговля','H':'Транспорт и хранение','other':'Иная специализация','diversified':'Нет выделенной специализации','few':'Менее 5 отчётных организаций','unobserved':'Нет адресных наблюдений'})
flat=pd.read_parquet(ROOT/'model/flat_gravity_membership.parquet').set_index('id').reindex(mem.id)
fc=flat.center_id.fillna('UNASSIGNED').to_numpy();nc=mem.center_id.fillna('UNASSIGNED').to_numpy()
rr=cent.set_index('id').root_id
fr=pd.Series(fc).map(rr).fillna('UNASSIGNED').to_numpy();nr=pd.Series(nc).map(rr).fillna('UNASSIGNED').to_numpy()
switch=np.where(fc==nc,0,np.where(fr==nr,1,2));switch[(fc=='UNASSIGNED')|(nc=='UNASSIGNED')]=3
draw('11_assignment_family_comparison','Чувствительность к семейству модели: nearest и гравитационное поле','Одинаковые кандидаты и исходная масса 2010. Совпадение центров и корней не является внешним подтверждением связей.',switch,{0:'#2374a1',1:'#82b8c6',2:'#ca665a',3:'#aeb5bb'},{0:'Тот же низовой центр',1:'Разные центры, общий корень',2:'Разные корневые системы',3:'Не назначено в одной из моделей'})
pc=np.digitize(np.log10(np.maximum(mem.potential.fillna(0),1e-12)),[0,1,2,3,4])
draw('12_population_potential','Потенциальное демографическое поле центров, 2010','Vᵢ = Σⱼ Pⱼ,2010 / (dᵢⱼ + 5 км)², d ≤100 км. Это сценарное поле, а не наблюдаемый поток.',pc,{0:'#d8e5ec',1:'#a6c9d8',2:'#6aa5c1',3:'#2f7ba4',4:'#1f4c73',5:'#ae5249'},{0:'V <1',1:'1–10',2:'10–100',3:'100–1 000',4:'1 000–10 000',5:'≥10 000'})

manifest=[{'file':p.name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'map':p.stem} for p in sorted(OUT.glob('[0-9][0-9]_*')) if p.suffix in ['.png','.svg','.pdf'] and '.tmp.' not in p.name]
(OUT/'manifest.json').write_text(json.dumps({'projection':T.target_crs.to_string(),'point_layer':'rasterized at250dpi,6000x3750 full map; boundaries and text vector inSVG/PDF','background_sha256':hashlib.sha256(args.background.read_bytes()).hexdigest(),'files':manifest},ensure_ascii=False,indent=2))
checks=[]
for x in manifest:
    p=OUT/x['file']
    if p.suffix=='.png':
        with Image.open(p) as im:im.verify()
    elif p.suffix=='.pdf':assert len(PdfReader(p).pages)==1
    else:
        import xml.etree.ElementTree as ET
        ET.parse(p)
    checks.append({'file':p.name,'passed':True})
(OUT/'format_checks.json').write_text(json.dumps(checks,indent=2))
w=PdfWriter()
for p in sorted(OUT.glob('[0-9][0-9]_*.pdf')):
    if '.tmp.' not in p.name:w.append(p)
atlas=OUT/'SGRT_MAP_ATLAS.pdf';temp=OUT/'SGRT_MAP_ATLAS.tmp.pdf'
with temp.open('wb') as f:w.write(f)
assert len(PdfReader(temp).pages)==len(manifest)//3
temp.replace(atlas)
print(json.dumps({'maps':len(manifest)//3,'files':len(manifest),'checks_passed':len(checks)},ensure_ascii=False))
