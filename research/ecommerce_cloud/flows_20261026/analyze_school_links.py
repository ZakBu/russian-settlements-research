#!/usr/bin/env python3
"""Aggregate public KOUZh school-location responses; no individual data output.

Input: same original individual members acquired by fetch_kouzh_inputs.py.
Location of school is not an identified administrative service centre.
"""
import argparse,csv,json,math
from collections import defaultdict
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]

def number(value):
    try:
        x=float(value.replace(',','.'))
        return x if math.isfinite(x) else None
    except (ValueError,AttributeError):return None

def code(value):
    x=number(value)
    return int(x) if x is not None and x==int(x) else None

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,default=ROOT/'work/ecommerce_flows_20261026')
    p.add_argument('--output',type=Path,default=HERE)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    cells=defaultdict(lambda:defaultdict(float));counts=defaultdict(lambda:defaultdict(int));times=defaultdict(list)
    participation=defaultdict(lambda:[0,0.0])
    for year in (2018,2022,2024):
        with (args.input/f'{year}_individual.csv').open(encoding='utf-8-sig',newline='') as f:
            for r in csv.DictReader(f,delimiter=';'):
                age=number(r['H01_02']);w=number(r['KVZV']);loc=code(r['H00_04']);size=code(r['R_1_1'])
                if w is None or w<=0 or age is None or loc not in (1,2):continue
                groups=['rural_all' if loc==2 else 'urban_all']
                if loc==2 and size in (7,8,9,10):groups.append(f'rural_size{size}')
                cohorts=[]
                if 7<=age<=14:
                    status=code(r['D03_23'])
                    if status in (1,2,3,4):
                        status_label='attendance'+str(status)
                    elif age<=8 and code(r['D02_22']) in (1,2,3,4,6):
                        status_label='no_attendance_code_structural_age7_8'
                    elif code(r['H01_12'])==99:
                        status_label='no_attendance_code_no_individual_interview'
                    else:
                        status_label='no_attendance_code_other'
                    for group in groups:
                        for label in ['all_children_age7_14', status_label]:
                            v=participation[(year,group,label)];v[0]+=1;v[1]+=w
                if 7<=age<=14 and code(r['D03_23'])==1:
                    cohorts.append(('attending_school_age7_14','D03_31'))
                if age>=15 and code(r['I07_05'])==1:
                    cohorts.append(('currently_enrolled_age15plus','I07_16'))
                for cohort,var in cohorts:
                    dest=code(r[var]);valid=dest in ((1,2) if var=='D03_31' else (1,2,3))
                    for group in groups:
                        key=(year,group,cohort);cells[key]['eligible']+=w;counts[key]['eligible']+=1
                        label=f'location{dest}' if valid else 'missing'
                        cells[key][label]+=w;counts[key][label]+=1
                        if var=='D03_31' and dest==2:
                            mode=code(r['D03_32']);mlabel=f'mode{mode}' if mode in (1,2,3,4,5) else 'mode_missing'
                            cells[key][mlabel]+=w;counts[key][mlabel]+=1
                            mins=number(r['D03_33'])
                            if mins is not None and mins>=0:times[key].append((mins,w))
    with (args.output/'school_participation.csv').open('w',newline='') as f:
        wr=csv.writer(f,lineterminator='\n');wr.writerow(['year','group','status','n','weighted_n'])
        for key,vals in sorted(participation.items()):wr.writerow([*key,*vals])
    rows=[]
    for key in sorted(cells):
        vals=cells[key];cnt=counts[key];validw=sum(vals[f'location{i}'] for i in (1,2,3));validn=sum(cnt[f'location{i}'] for i in (1,2,3))
        row=dict(year=key[0],group=key[1],cohort=key[2],n_eligible=cnt['eligible'],weighted_eligible=vals['eligible'],n_valid_location=validn,weighted_valid_location=validw,n_other_settlement=cnt['location2'],weighted_other_settlement=vals['location2'],pct_other_all_eligible=100*vals['location2']/vals['eligible'],pct_other_valid=100*vals['location2']/validw if validw else None,pct_missing=100*vals['missing']/vals['eligible'])
        if key[2]=='attending_school_age7_14':
            for m in (1,2,3,4,5):row[f'pct_mode{m}_among_other']=100*vals[f'mode{m}']/vals['location2'] if vals['location2'] else None
            row['pct_mode_missing_among_other']=100*vals['mode_missing']/vals['location2'] if vals['location2'] else None
            a=sorted(times[key]);half=sum(w for _,w in a)/2;acc=0;median=None
            for t,w in a:
                acc+=w
                if acc>=half:median=t;break
            row['weighted_median_minutes_other']=median
            row['n_time_valid_other']=len(a)
        rows.append(row)
    for cohort,filename in [('attending_school_age7_14','school_locations.csv'),('currently_enrolled_age15plus','education_locations_15plus.csv')]:
        select=[r for r in rows if r['cohort']==cohort];fields=list(dict.fromkeys(k for row in select for k in row))
        with (args.output/filename).open('w',newline='') as f:
            wr=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');wr.writeheader();wr.writerows(select)
    print(json.dumps([r for r in rows if r['group'] in ['rural_all','urban_all']],ensure_ascii=False,indent=2))
if __name__=='__main__':main()
