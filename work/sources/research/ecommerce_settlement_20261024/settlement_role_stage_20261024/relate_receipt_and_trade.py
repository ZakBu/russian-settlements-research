"""Descriptive co-occurrence of receipt dispersion and trade concentration.

Different catalogue windows and shop-reporting periods are retained explicitly.
No treatment/control or causal effect is constructed from catalogue evidence.
"""
from pathlib import Path
import json
import pandas as pd

OUT=Path(__file__).resolve().parent
KEY='source_record_id_2021'


def main():
    c=pd.read_csv(OUT/'bdmo/singleton/internal_centre_district_common_panels2022_2024.csv')
    c=c.loc[c.medium_primary2002].copy()
    assert not c.duplicated([KEY,'category']).any()
    sensitivities=[]
    for category,g in c.groupby('category'):
        x=g.centre_share_change2022_2024_pp
        for threshold in [0,1,2,5]:
            loss=x.lt(-1e-9) if threshold==0 else x.le(-threshold)
            gain=x.gt(1e-9) if threshold==0 else x.ge(threshold)
            sensitivities.append(dict(
                category=category,share_threshold_pp=threshold,centres_n=len(g),
                share_loss_n=int(loss.sum()),share_gain_n=int(gain.sum()),
                share_between_thresholds_n=int((~loss & ~gain).sum()),
                centre_stock_decline_n=int(g.centre_stock_change2022_2024.lt(0).sum()),
                stock_decline_and_share_loss_n=int((g.centre_stock_change2022_2024.lt(0)&loss).sum()),
                median_share_change_pp=x.median(),
            ))
    pd.DataFrame(sensitivities).to_csv(OUT/'trade_share_threshold_sensitivity.csv',index=False)
    fields=[KEY,'first','last','comparison','radius_km','profile',
            'other_positive_member_change_n','centre_objects_before','centre_objects_after']
    network=pd.read_csv(OUT/'system/centre_context_typology.csv',usecols=fields)
    network=network.loc[network['first'].eq('2022-09-29') & network['last'].eq('2024-03-11')]
    assert not network.duplicated([KEY,'radius_km','profile']).any()
    joined=pd.concat([g.merge(network,on=KEY,validate='one_to_many')
                      for _,g in c.groupby('category')],ignore_index=True)
    assert not joined.duplicated([KEY,'category','radius_km','profile']).any()
    joined['centre_catalogue_record_both_dates']=(
        joined.centre_objects_before.gt(0)&joined.centre_objects_after.gt(0))
    joined['receipt_category']=joined.other_positive_member_change_n.gt(0).map({
        True:'net_increase_in_other_positive_catalogue_NP',
        False:'no_net_increase_in_other_positive_catalogue_NP'})
    # Keep all joined observations; the comparison table uses only positively
    # witnessed central catalogue records on BOTH dates, never confirmed absence.
    joined['trade_period']='IVquarter2022_to_IVquarter2024'
    joined['causal_effect_identified']=False
    joined['source_windows_time_aligned']=False
    joined.to_csv(OUT/'receipt_trade_descriptive_pairs.csv',index=False)
    summaries=[]
    usable=joined.loc[joined.centre_catalogue_record_both_dates]
    for keys,g in usable.groupby(['category','radius_km','profile','receipt_category']):
        category,radius,profile,receipt=keys
        x=g.centre_share_change2022_2024_pp
        summaries.append(dict(
            category=category,radius_km=radius,catalogue_profile=profile,
            receipt_category=receipt,centres_n=len(g),
            stock_decline_n=int(g.centre_stock_change2022_2024.lt(0).sum()),
            share_loss_atleast1pp_n=int(x.le(-1).sum()),
            share_gain_atleast1pp_n=int(x.ge(1).sum()),
            share_between_minus1_plus1pp_n=int(x.between(-1,1,inclusive='neither').sum()),
            median_trade_share_change_pp=x.median(),
            catalogue_window='2022-09-29_to_2024-03-11',
            trade_window='IVquarter2022_to_IVquarter2024',
            source_profiles_harmonized=False,causal_interpretation=False,
        ))
    s=pd.DataFrame(summaries)
    assert (s.share_loss_atleast1pp_n+s.share_gain_atleast1pp_n+
            s.share_between_minus1_plus1pp_n==s.centres_n).all()
    s.to_csv(OUT/'receipt_trade_descriptive_summary.csv',index=False)
    audit={
        'trade_panel_medium_by_category':c.groupby('category')[KEY].nunique().to_dict(),
        'joined_rows':len(joined),'positive_centre_both_dates_rows':len(usable),
        'main5km_allcatalog':s.loc[s.radius_km.eq(5)&s.catalogue_profile.eq('allcatalog_objects')].to_dict('records'),
        'checks':'PASS unique centre-category and centre-radius-profile keys; one-to-many join; category sums',
        'limitations':[
            'Shop C/S is lower-municipal-unit stock divided by whole district; exact NP interpretation remains conditional.',
            'Singleton status witnessed in2020/2021/2022/2026, not verified for every2023/2024 observation.',
            'Administrative context and reported store counts do not measure customer catchments or trade capacity.',
            'Positive catalogue-node change is not a measured change of the complete operating network.',
            'Catalogue and trade windows differ and source profiles are not fully harmonized.',
            'Groups are descriptive observed categories, not treated/control groups; no platform effect estimated.',
        ],
    }
    (OUT/'receipt_trade_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(audit['main5km_allcatalog'],ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
