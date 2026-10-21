"""Versioned display repair: remove unavailable context-population column on page 10.
All other 39 PNGs must remain byte-identical; no classification/source changes.
"""
from pathlib import Path
import argparse,json,hashlib,shutil,os,importlib.util,tempfile
import pandas as pd,numpy as np,fitz
P=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 a=argparse.ArgumentParser();a.add_argument('--parent',required=True);a.add_argument('--config',required=True);a.add_argument('--output',required=True);v=a.parse_args();src=Path(v.parent);dest=Path(v.output);cp=Path(v.config);assert not dest.exists();prior=json.loads((src/'atlas_receipt.json').read_text());assert prior['config_sha256']==sha(cp);cfg=json.loads(cp.read_text());spec=importlib.util.spec_from_file_location('held_v8',P/'render_atlas_v8.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r);n,u,z,w=r.load(cfg,True)
 shutil.copytree(src,dest,copy_function=os.link)
 def write(p,text):
  if p.exists():p.unlink()
  p.write_text(text)
 mainr=prior['volumes']['main'];selected=mainr['views'];u=u[u.level.isin(selected)];z=z[z.level.isin(selected)]
 with tempfile.TemporaryDirectory(prefix='sgrt_quality_page_')as td:
  td=Path(td);a=r.Atlas(td,n,u,z,cfg,w);a.pages=[{}]*9;fig,axs=r.plt.subplots(1,2,figsize=(14,10));quality=[]
  for level,g in u.groupby('level'):
   den=pd.to_numeric(g.population2010_known_denominator,errors='coerce');share=pd.to_numeric(g.protected_secondary2010_population_share,errors='coerce');good=den.gt(0)&share.notna();total=den[good].sum();quality.append({'level':level,'n_units':len(g),'units_with_missing_additive2010':int(g['2010_missing_population_count'].gt(0).sum()),'secondary_share_of_known_population2010':float((den[good]*share[good]).sum()/total)if total>0 else np.nan,'known_population2010_denominator':float(total)})
  q=pd.DataFrame(quality);cells=[[r.textwrap.fill(cfg['view_metadata'][row.level]['label'],22),str(row.n_units),str(row.units_with_missing_additive2010),f'{100*row.secondary_share_of_known_population2010:.1f}%'if np.isfinite(row.secondary_share_of_known_population2010)else'Неизвестно']for row in q.itertuples()];axs[0].axis('off');headers=[r.textwrap.fill(s,20)for s in ['Представление','Единиц','Есть пропуски населения 2010','Доля вторичного в известном P2010']];table=axs[0].table(cellText=cells,colLabels=headers,colWidths=[.37,.13,.24,.26],loc='center',cellLoc='left');table.auto_set_font_size(False);table.set_fontsize(8)
  for cell in table.get_celld().values():cell.set_height(.105)
  axs[0].set_title('Каждое представление: отдельный знаменатель',fontsize=10)
  for level,g in u.groupby('level'):axs[1].hist(g.protected_secondary2010_population_share.dropna(),bins=np.linspace(0,1,21),histtype='step',label=cfg['view_metadata'][level]['label'])
  axs[1].set_title('Источниковая доля внутри отдельной единицы',fontsize=10);axs[1].set_xlabel('Вторичное / известное аддитивное население 2010');axs[1].set_ylabel('Единиц данного представления');axs[1].legend(fontsize=7)
  a.finish(fig,'Географическая и источниковая полнота','Каждая строка — отдельное представление, без суммирования альтернатив. Доля вторичного населения взвешена известным неотрицательным аддитивным населением 2010 внутри этой строки; полный знаменатель сохранён в source_quality_by_view.csv. Здесь показано качество аддитивного населения; собственное население контекстных городов в эту сумму не подставляется. Нулевой знаменатель остаётся неизвестным.','source_quality');a.pdf.close();newpage=a.pages[-1]
  png=dest/'main'/newpage['png'];png.unlink();shutil.copyfile(td/newpage['png'],png);qualitypath=dest/'main/source_quality_by_view.csv';qualitypath.unlink();q.to_csv(qualitypath,index=False)
  pdf=fitz.open(src/'main/atlas_cycle07.pdf');replacement=fitz.open(td/'atlas_cycle07.pdf');assert len(replacement)==1;pdf.delete_page(9);pdf.insert_pdf(replacement,start_at=9);p=dest/'main/atlas_cycle07.pdf';p.unlink();pdf.save(p);pdf.close()
 oldpages=prior['volumes']['main']['pages'];assert oldpages[9]['kind']=='source_quality';oldpages[9]=newpage
 vrpath=dest/'main/render_receipt.json';vr=json.loads(vrpath.read_text());vr['pages']=oldpages;vr['parent_render_receipt_sha256']=sha(src/'main/render_receipt.json');vr['versioned_display_patch_code_sha256']=sha(__file__);vr['files']={p.name:sha(p)for p in (dest/'main').iterdir()if p.is_file()and p.name!='render_receipt.json'};write(vrpath,json.dumps(vr,ensure_ascii=False,indent=2))
 prior['volumes']['main']['files']={p.name:sha(p)for p in(dest/'main').iterdir()if p.is_file()};unchanged=[]
 for volume in ['main','operational_supplement']:
  for p in(src/volume).glob('*.png'):
   if volume=='main'and p.name==newpage['png']:continue
   assert sha(p)==sha(dest/volume/p.name);unchanged.append(str(p.relative_to(src)))
 assert len(unchanged)==39
 prior['parent_atlas_receipt_sha256']=sha(src/'atlas_receipt.json');prior['versioned_display_patch']={'code_sha256':sha(__file__),'removed_unavailable_column':'units_with_unknown_metropolitan_own2010','unchanged_pngs':unchanged,'all39_other_pngs_exact':True,'population_context_scope':'Only known additive 2010 population quality; no all-context/focal substitution'};prior['files']={p.name:sha(p)for p in dest.iterdir()if p.is_file()and p.name!='atlas_receipt.json'};write(dest/'atlas_receipt.json',json.dumps(prior,ensure_ascii=False,indent=2));assert all(sha(p)==h for p,h in w.items());print(dest)
if __name__=='__main__':main()
