#!/usr/bin/env python3
"""Visualize legal-registration evidence and linkage coverage, never object counts."""
import argparse,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import pandas as pd
from build_dynamics import sha,dump
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--data',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--address-audit',type=Path);a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 d=pd.read_csv(a.data/'coverage_2011_2025.csv').sort_values('year');assert d.year.tolist()==list(range(2011,2026))
 plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,'axes.spines.right':False,'axes.spines.left':False,'axes.spines.bottom':False,'axes.titleweight':'bold','axes.labelcolor':'#374b5a','text.color':'#183244','xtick.color':'#506371','ytick.color':'#506371','grid.color':'#dfe7ed'})
 fig,axes=plt.subplots(3,1,figsize=(12,10),sharex=True)
 specs=[('points_with_direct_service_witness','НП хотя бы с одной сервисной группой','#1865a6'),('points_with_ge2_direct_groups','НП с двумя и более сервисными группами','#3e88b9'),('points_with_ge3_direct_groups','НП с тремя и более сервисными группами','#77a9cc')]
 for ax,(column,title,color) in zip(axes,specs):
  ax.plot(d.year,d[column],color=color,lw=2.8,marker='o',markersize=4.5)
  ax.set_title(title,loc='left',pad=12,fontsize=12);ax.grid(axis='y');ax.set_axisbelow(True)
  ax.yaxis.set_major_formatter(FuncFormatter(lambda x,_:f'{int(x):,}'.replace(',',' ')))
  for row in [d.iloc[0],d.iloc[-1]]:
   offset=(0,-18) if a.address_audit and row.year==2025 else (0,10)
   ax.annotate(f'{int(row[column]):,}'.replace(',',' '),(row.year,row[column]),xytext=offset,textcoords='offset points',ha='center',fontsize=10,fontweight='bold',color=color)
  ax.margins(y=.3)
 if a.address_audit:
  adj=pd.read_csv(a.address_audit/'annual_vs_yearend_date_sensitivity.csv').query('mode=="conditional_alias_annual_2025"').iloc[0]
  for ax,col in zip(axes,['points_direct_service_witness','points_ge2_direct_groups','points_ge3_direct_groups']):
   value=int(adj[col]);ax.scatter([2025],[value],marker='^',s=75,facecolors='white',edgecolors='#bd742e',linewidths=1.8,zorder=5,label='2025: условная кодовая сверка')
   ax.annotate(f'{value:,}'.replace(',',' '),(2025,value),xytext=(0,9),textcoords='offset points',ha='center',fontsize=10,fontweight='bold',color='#a2632d')
  axes[0].legend(loc='upper right',frameon=False,fontsize=10)
 axes[-1].set_xticks([2011,2014,2017,2020,2023,2025]);axes[-1].set_xlim(2010.6,2025.4)
 fig.suptitle('Юридические свидетельства сервисных функций, 2011–2025',x=.08,y=.975,ha='left',fontsize=17,fontweight='bold')
 fig.text(.08,.927,'Одна и та же ось 142 570 НП · точный код ОКТМО · единая версия RFSD',fontsize=11,color='#506371')
 fig.subplots_adjust(left=.08,right=.97,top=.87,bottom=.13,hspace=.46)
 caption='Семь групп: розница, питание, образование, медицина, социальные услуги, ремонт, персональные услуги.\nЮридическая регистрация не равна физическим объектам, их мощности или внешним связям.\nОсь кодов — 2021; историческая преемственность кодов полностью не установлена. Москва и Санкт-Петербург вне оси.'
 if a.address_audit:caption+='\nТреугольник: отдельная чувствительность 2025 по многократно проверенным кодовым соответствиям; основной ряд сохранён.'
 fig.text(.08,.035 if a.address_audit else .055,caption,fontsize=9,color='#506371',linespacing=1.5)
 for ext in ['png','svg','pdf']:fig.savefig(a.out/f'legal_function_calendar_2011_2025.{ext}',dpi=250,facecolor='white')
 plt.close(fig)
 fig,axes=plt.subplots(2,1,figsize=(12,7.8),sharex=True)
 axes[0].plot(d.year,d.valid_inn_rows/1e6,color='#1865a6',marker='o',lw=2.6);axes[0].set_ylabel('Миллионов ИНН');axes[0].set_title('Состав источника: юридические лица в годовом RFSD',loc='left');axes[0].grid(axis='y')
 ratio=100*d.exact_settlement_code_entities/d.valid_inn_rows
 axes[1].plot(d.year,ratio,color='#3e88b9',marker='o',lw=2.6);axes[1].set_ylabel('% годовых ИНН');axes[1].set_title('Доля ИНН, связанных с обычными НП по точному коду',loc='left');axes[1].grid(axis='y');axes[1].set_xticks([2011,2014,2017,2020,2023,2025])
 fig.subplots_adjust(left=.08,right=.97,top=.91,bottom=.17,hspace=.43)
 fig.text(.08,.055,'Это контроль состава и связки источника, а не доля охваченных физических услуг.\nВ знаменателе присутствуют федеральные города и прочие записи за пределами фиксированной оси обычных НП.\nИсточник: RFSD, commit bde9b8b129a8be582b66de4e30ed79c9187a8515; извлечены пять колонок.',fontsize=9,color='#506371',linespacing=1.5)
 for ext in ['png','svg','pdf']:fig.savefig(a.out/f'RFSD_calendar_coverage.{ext}',dpi=250,facecolor='white')
 plt.close(fig)
 dump(a.out/'FIGURE_MANIFEST.json',{f.name:{'sha256':sha(f),'bytes':f.stat().st_size} for f in a.out.iterdir() if f.is_file() and f.name!='FIGURE_MANIFEST.json'})
 print('Six figure files generated; visual inspection still required.')
if __name__=='__main__':main()
