"""A true municipal time comparison, explicitly not a SGRT time comparison."""
from pathlib import Path
import pandas as pd
r=Path(__file__).resolve().parent
x=pd.read_csv(r/'lower_municipal_profiles.csv',dtype={'municipality_code':str})
w=x[x.year.isin([2008,2009])].pivot(index=['municipality_code','municipality'],columns='year',values='household_sown_total_reported_ha').reset_index()
w['delta_ha']=w[2009]-w[2008]
w['change_percent']=100*(w[2009]/w[2008]-1)
w['scope']='whole_municipality_households_not_2025_functional_fragment'
w.to_csv(r/'municipal_household_sown_change_2008_2009.csv',index=False)
