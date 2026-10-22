#!/usr/bin/env python3
from pathlib import Path
import json
import numpy as np,pandas as pd
from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from recover_bonitet import design,ROOT,SOURCE

r=json.loads((ROOT/'recovery_receipt.json').read_text());g=pd.read_csv(ROOT/'control_points_linked.csv')
p=np.asarray(r['final_spherical_conic_params']);B=np.asarray(r['final_affine_matrix']);kind=r['selected_projection_family']
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11})
fig,ax=plt.subplots(figsize=(16,9));ax.imshow(Image.open(SOURCE));ax.set_xlim(760,2500);ax.set_ylim(1200,240)
for lat in [40,50,60,70,80]:
 lon=np.linspace(20,191,400);xy=design(lon,np.full(len(lon),lat),kind,p)@B;ax.plot(xy[:,0],xy[:,1],c='#0066cc',lw=.7,ls=':',alpha=.7)
for lon in np.arange(20,191,10):
 lat=np.linspace(40,82,200);xy=design(np.full(len(lat),lon),lat,kind,p)@B;ax.plot(xy[:,0],xy[:,1],c='#0066cc',lw=.7,ls=':',alpha=.7)
for role,color,label in [('train','#264653','Обучающие опоры: 33'),('holdout','#d62828','Отложенные опоры: 12')]:
 z=g[g.role.eq(role)];ax.scatter(z.pixel_x,z.pixel_y,marker='o',facecolors='none',edgecolors=color,s=70,lw=1.2,label=label)
ax.legend(loc='lower left',framealpha=.95);ax.axis('off');ax.set_title('Экспериментальная геопривязка первичной карты бонитета',loc='left',fontsize=17,pad=14)
fig.text(.125,.06,'Национальный атлас почв РФ, с. 240–241, масштаб 1:30 млн. Синий пунктир — восстановленная координатная сетка.\n45 точечных знаков городов; RMSE на 12 отложенных опорах — 19,3 км. Это техническая привязка, не измерение почв в городах.',fontsize=10)
fig.savefig(ROOT/'georeference_diagnostic.png',dpi=180,bbox_inches='tight');fig.savefig(ROOT/'georeference_diagnostic.pdf',bbox_inches='tight');plt.close(fig)
