exec(open('work/make_maps.py').read().split('# Three periods')[0])
D=pd.read_parquet('work/sources/commerce_current.parquet');D=A[['id','lat','lon']].merge(D,on='id',validate='one_to_one')
fig,axs=panel(6)
spec=[('Wildberries · выбранные типы доставки','commerce_wb20261021_baseline_focus_count'),('Магазины · каталог Places','places_baseline_retail_store_count'),('Общепит · каталог Places','places_baseline_food_service_count'),('Ozon · только сигналы названия','commerce_ozon_name_signal_not_verified_pvz_count'),('Зарегистрированная розница · 2021','econ_native_2021_retail47_legal_entities'),('Зарегистрированный общепит · 2021','econ_native_2021_food56_legal_entities')]
for ax,(title,col) in zip(axs.flat,spec):
 base(ax,title);d=D[D[col].gt(0)&D.lat.notna()&D.lon.notna()];point(ax,d,'#287a97' if not 'Ozon' in title else '#dca147',s=5);ax.text(.01,.02,f'{len(d):,} НП с записью'.replace(',',' '),transform=ax.transAxes,fontsize=11,bbox=dict(fc='white',ec='none',alpha=.9))
save(fig,'modern_commerce')
# Keep source figure intact; make a two-panel transport extract for readable report composition.
from PIL import Image
im=Image.open(ROOT/'maps/01_axis_road_coverage.png');im.crop((0,1260,2029,2470)).save(OUT/'transport_extract.png')
