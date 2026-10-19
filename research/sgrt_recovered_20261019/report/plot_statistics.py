"""Plot exactly the independently checked spatial OOF comparison intervals."""
from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
R=Path(__file__).resolve().parent.parent;O=R/'report'
ordinary=json.loads((R/'statistics/functional_incremental_validation.json').read_text())
buffer=json.loads((R/'statistics/buffer50_validation.json').read_text())
plt.rcParams.update({'font.family':'DejaVu Sans','pdf.fonttype':42,'svg.fonttype':'none'})
fig,axs=plt.subplots(1,2,figsize=(13,7.5),sharex=True)
for ax,outcome,title in zip(axs,['outcome_total','outcome_environment'],['Весь район: 4 262 системы','Окружение: 3 931 система']):
    for i,(size,label,data) in enumerate([(250,'Блоки 250 км',ordinary),(400,'Блоки 400 км',ordinary),(600,'Блоки 600 км',ordinary),(400,'400 км + буфер 50 км',buffer)]):
        for comp,offset,color in [('M2 minus M1',-.12,'#9b9fa3'),('M3 minus M2',.12,'#2478a6')]:
            row=next(x for x in data['results'] if x.get('comparison')==comp and x['outcome']==outcome and x['block_km']==size)
            x=row['delta_MSE'];y=3-i+offset
            ax.errorbar(x,y,xerr=[[x-row['CI025']],[row['CI975']-x]],fmt='o',color=color,capsize=4,elinewidth=2,markersize=5,label=('Аграрный блок: M2−M1' if comp=='M2 minus M1' else 'RFSD: M3−M2') if i==0 else None)
    ax.axvline(0,color='#7a8a95',lw=1,ls='--');ax.set_yticks([3,2,1,0],['250 км','400 км','600 км','400 км + 50 км']);ax.set_title(title,loc='left',weight='bold',pad=15);ax.grid(axis='x',color='#e0e6ea');ax.set_axisbelow(True)
    for k in ['top','right','left']:ax.spines[k].set_visible(False)
    ax.set_xlabel('ΔMSE: отрицательное значение означает меньшую ошибку')
axs[0].legend(loc='upper left',bbox_to_anchor=(-.05,1.24),frameon=False,ncol=2)
fig.suptitle('Дополнительная информация и пространственная неопределённость',x=.07,y=.985,ha='left',fontsize=17,weight='bold')
fig.text(.07,.025,'Пять пространственных folds; 399 парных выборок целых блоков. Интервалы условны на обученных моделях. Ретроспективная ассоциация, не причинный эффект.',fontsize=8.5,color='#566776')
fig.subplots_adjust(left=.12,right=.98,top=.79,bottom=.13,wspace=.34)
for ext in ['png','svg','pdf']:fig.savefig(O/('spatial_increment.'+ext),dpi=240)
plt.close(fig)
