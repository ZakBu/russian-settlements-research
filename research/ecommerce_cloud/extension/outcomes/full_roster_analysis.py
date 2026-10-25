"""Compare newly recovered full official publication rosters with fixed contexts.

Publication snapshots are not certified Jan-1 boundaries. The second view is
a target-date candidate reconstruction: future DateVved rows use an earlier
same-code published state only when available and dated no later than target;
otherwise the publication row is retained. ALL future-row contexts remain
flagged temporally ambiguous, including those with previous-state substitution.
No Status value is interpreted as deletion; no unknown code is blindly dropped.
"""
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime, date
import csv, hashlib, io, json, re, unicodedata
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
BASE = ROOT / "work/sources/research/ecommerce_settlement_20261024"
SINGLE = BASE / "settlement_role_stage_20261024/bdmo/singleton"
NEW = ROOT / "work/ecommerce_rosters_verified"
PANELDIR = ROOT / "work/ecommerce_extension_outcomes/nonshop_population_contexts"
OUT = PANELDIR / "roster_analysis"
OUT.mkdir(parents=True, exist_ok=True)
KEY = "source_record_id_2021"
FIELDS = ["TER","KOD1","KOD2","KOD3","KC","RAZDEL","NAME1","Centrum",
          "NomDescr","NomAkt","Status","DateUtv","DateVved"]
SPECS = [
 ("20221228", "2023-01-01", "9231da45adddb6e9aa190d21224885e60af773bdb91240635cbded3b7e65ccb5"),
 ("20231219", "2024-01-01", "8be058baf8d8ec32bda5431fa6ed5ccdcf0effa0c62869a03576755cbcf956d9"),
 ("20241227", "2025-01-01", "513bd287a1f1b42b9190f04afcfb8239bd31e0e699bb890f67dc49341285c13b"),
]
def true(v):
 return str(v).strip().casefold() in {"true","1"}
def norm(v):
 return re.sub(r"\s+"," ",unicodedata.normalize("NFKC",str(v)).casefold().replace("ё","е")).strip()
def dt(v):
 try: return datetime.strptime(v,"%d.%m.%Y").date()
 except (ValueError,TypeError): return None
def rowkey(r): return r["RAZDEL"],r["TER"]+r["KOD1"]+r["KOD2"]+r["KOD3"]
def parse(path):
 data=path.read_bytes()
 try: text=data.decode("utf-8-sig");enc="utf-8-sig"
 except UnicodeDecodeError: text=data.decode("cp1251");enc="cp1251"
 rows=[]
 for n,row in enumerate(csv.reader(io.StringIO(text),delimiter=";"),1):
  if len(row)==13 and all(row[j].isdigit() for j in range(4)):
   r=dict(zip(FIELDS,row),source_row=n)
   assert [len(r[k]) for k in FIELDS[:4]]==[2,3,3,3],(path,n)
   rows.append(r)
 assert len({rowkey(r) for r in rows})==len(rows),(path,"duplicate section/code")
 return rows,{"path":str(path.relative_to(ROOT)),"sha256":hashlib.sha256(data).hexdigest(),
              "parsed_rows":len(rows),"encoding":enc,
              "status_counts":dict(Counter(r["Status"] for r in rows))}
def find_one(folder,vintage):
 paths=sorted(folder.rglob("data-"+vintage+"T*.csv"))
 assert len(paths)==1,(folder,vintage,[str(p) for p in paths])
 return paths[0]
def build(rows,uncertain=None):
 np5,np8=defaultdict(dict),defaultdict(dict)
 mo=set()
 for r in rows:
  code=rowkey(r)[1]
  if r["RAZDEL"]=="2" and r["KOD3"]!="000":
   np5[code[:5]][code]=norm(r["NAME1"])
   np8[code[:8]][code]=norm(r["NAME1"])
  # Group headers KOD1 ...00 and lower KOD2 ...00 are never real MO.
  if (r["RAZDEL"]=="1" and r["KOD3"]=="000"
      and r["KOD1"]!="000" and not r["KOD1"].endswith("00")
      and (r["KOD2"]=="000" or not r["KOD2"].endswith("00"))):
   mo.add(code[:8])
 return {"np5":np5,"np8":np8,"mo":mo,"uncertain":uncertain or set()}
def composition(snap,codes,lower=False):
 roster={}
 present=all(c in snap["mo"] for c in codes)
 ambiguous=False
 for c in codes:
  g=snap["np8"].get(c,{}) if lower else snap["np5"].get(c[:5],{})
  for code,name in g.items():
   assert code not in roster,(codes,code,"overlapping fixed municipality rosters")
   roster[code]=name
  ambiguous |= any(u[:8]==c if lower else u[:5]==c[:5] for u in snap["uncertain"])
 return roster,present,ambiguous
def sig(roster,names):
 values=sorted(roster.items()) if names else sorted(roster)
 return hashlib.sha256(json.dumps(values,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
inputs=[]; oldrows={}; snapshots={}
manifest=json.loads((ROOT/"research/ecommerce_cloud/data_manifest.json").read_text())
pins={r["path"]:r["sha256"] for r in manifest["files"]}
for v in ["20200110","20211103","20220927"]:
 path=find_one(BASE/"history_stage_20261024/centres/raw",v)
 rows,audit=parse(path);assert pins[str(path.relative_to(ROOT))]==audit["sha256"]
 inputs.append(audit);oldrows[v]=rows;snapshots[("publication",v)]=build(rows)
previous={}
for v in sorted(oldrows):
 snapshot_date=datetime.strptime(v,"%Y%m%d").date()
 for r in oldrows[v]:
  d=dt(r["DateVved"])
  if d is not None and d<=snapshot_date: previous[rowkey(r)]=r
future_audit=[]
for vintage,target,expected in SPECS:
 path=find_one(NEW,vintage);rows,audit=parse(path)
 assert audit["sha256"]==expected,(path,audit["sha256"])
 audit.update(publication_filename_date=vintage,target_candidate_date=target,
              filename_date_is_not_verified_effective_date=True)
 inputs.append(audit)
 targetdate=date.fromisoformat(target)
 candidate=[];unresolved=set()
 for r in rows:
  d=dt(r["DateVved"]); key=rowkey(r); code=key[1]
  if d is not None and d>targetdate:
   prior=previous.get(key)
   accepted=(prior is not None and dt(prior["DateVved"]) is not None
             and dt(prior["DateVved"])<=targetdate)
   candidate.append(prior if accepted else r)
   unresolved.add(code)
   future_audit.append({
    "publication":vintage,"target_candidate_date":target,"code11":code,
    "RAZDEL":r["RAZDEL"],"NAME1":r["NAME1"],"Status":r["Status"],
    "DateUtv":r["DateUtv"],"DateVved":r["DateVved"],
    "candidate_action":"previous_same_code_state" if accepted else "retain_publication_row_UNRESOLVED",
    "previous_NAME1":prior["NAME1"] if prior else "",
    "previous_Status":prior["Status"] if prior else "",
    "previous_DateVved":prior["DateVved"] if prior else "",
   })
  else: candidate.append(r)
 snapshots[("publication",vintage)]=build(rows,unresolved)
 snapshots[("Jan1_candidate",vintage)]=build(candidate,unresolved)
 # Prior source state is updated only from rows already in force by this
 # PUBLICATION filename date; that date itself is not a boundary claim.
 publication_date=datetime.strptime(vintage,"%Y%m%d").date()
 for r in rows:
  d=dt(r["DateVved"])
  if d is not None and d<=publication_date: previous[rowkey(r)]=r
pd.DataFrame(future_audit).to_csv(OUT/"future_rows_previous_state_audit.csv",index=False)
candidates=pd.read_csv(SINGLE/"internal_singleton_centre_district_candidates.csv",
                       dtype=str,keep_default_na=False)
assert len(candidates)==338
relations=pd.read_csv(PANELDIR/"registry_relations_before_selection.csv",
                     dtype=str,keep_default_na=False)
assert len(relations)==1953
shops=pd.read_csv(SINGLE/"internal_centre_district_common_panels2022_2024.csv",
                   dtype=str,keep_default_na=False)
shops=shops.loc[shops.category.eq("Магазины") & shops.medium_primary2002.map(true)].copy()
assert shops[KEY].is_unique and len(shops)==174
old174ids=set(shops[KEY])
assert len(old174ids)==174
contexts=[]
for r in candidates.to_dict("records"):
 contexts.append({"scope":"lower338","context_id":r[KEY],KEY:r[KEY],
                  "codes":[r["oktmo"]],"lower":True,
                  "name_2021":r.get("name_2021",""),
                  "parent_codes":[r["parent_oktmo"]]})
 contexts.append({"scope":"lower338_parents","context_id":r[KEY],KEY:r[KEY],
                  "codes":[r["parent_oktmo"]],"lower":False,
                  "name_2021":r.get("name_2021","")})
for r in relations.to_dict("records"):
 contexts.append({"scope":"upper1953","context_id":r[KEY],KEY:r[KEY],
                  "codes":r["upper_municipality_codes2020"].split(","),
                  "lower":False,"name_2021":r["name_2021"]})
for r in shops.to_dict("records"):
 for scope,column,lower in [
     ("old174_centre_units","centre_oktmo",True),
     ("old174_parent_units","district_oktmo",False)]:
  code=r[column]
  assert re.fullmatch(r"\d{8}",code)
  contexts.append({"scope":scope,"context_id":r[KEY],KEY:r[KEY],
                   "codes":[code],"lower":lower,"name_2021":r["name_2021"]})
comparisons=[]; roster_lists=[]; eligibility={}
for ctx in contexts:
 codes=ctx["codes"];lower=ctx["lower"]
 refs={}
 for ref in ["20200110","20211103"]:
  rr,present,_=composition(snapshots[("publication",ref)],codes,lower)
  refs[ref]=(rr,present)
 for view in ["publication","Jan1_candidate"]:
  all_codes_stable=True;all_names_stable=True;all_unambiguous=True
  all_singleton_reference=True
  for vintage,target,_ in SPECS:
   rr,present,amb=composition(snapshots[(view,vintage)],codes,lower)
   row={"scope":ctx["scope"],"context_id":ctx["context_id"],KEY:ctx[KEY],
        "view":view,"publication":vintage,"target_candidate_date":target,
        "fixed_municipality_codes2020":",".join(codes),
        "fixed_municipalities_present":present,"np_count":len(rr),
        "codes_sha256":sig(rr,False),"names_sha256":sig(rr,True),
        "future_state_unresolved":amb}
   for ref,(old,pres) in refs.items():
    codeequal=present and pres and set(rr)==set(old)
    nameequal=codeequal and rr==old
    row["code_set_equal_"+ref]=codeequal
    row["code_name_set_equal_"+ref]=nameequal
    row["added_codes_vs"+ref]=json.dumps(sorted(set(rr)-set(old)))
    row["removed_codes_vs"+ref]=json.dumps(sorted(set(old)-set(rr)))
    all_codes_stable &= codeequal;all_names_stable &= nameequal
   all_unambiguous &= not amb
   reference=refs["20211103"][0]
   eligible=(present and len(rr)==1 and len(reference)==1 and rr==reference)
   row["same_singleton_code_name_as20211103"]=eligible
   all_singleton_reference &= eligible
   comparisons.append(row)
   for code,name in sorted(rr.items()):
    roster_lists.append({"scope":ctx["scope"],"context_id":ctx["context_id"],
      "view":view,"publication":vintage,"np_code11":code,"normalized_name":name})
  eligibility[(ctx["scope"],ctx["context_id"],view)]={
    KEY:ctx[KEY],
    "code_sets_unchanged_vs2020_2021":bool(all_codes_stable),
    "code_name_sets_unchanged_vs2020_2021":bool(all_names_stable),
    "no_future_rows_affect_context":bool(all_unambiguous),
    "same_singleton_all3_publications":bool(all_singleton_reference)}
pd.DataFrame(comparisons).to_csv(OUT/"fixed_context_roster_comparisons.csv",index=False)
pd.DataFrame(roster_lists).to_csv(OUT/"full_fixed_context_roster_lists.csv",index=False)
eligrows=[{"scope":scope,"context_id":context_id,"view":view,**v}
          for (scope,context_id,view),v in eligibility.items()]
eligframe=pd.DataFrame(eligrows)
eligframe.to_csv(OUT/"three_publication_eligibility.csv",index=False)
old170=pd.read_csv(ROOT/"research/ecommerce_cloud/extension/outcomes/recent_population_panels.csv")
old170ids=set(old170.loc[old170.medium_primary2002.map(true),KEY])
shops=pd.read_csv(SINGLE/"internal_centre_district_common_panels2022_2024.csv",
                   dtype=str,keep_default_na=False)
shops=shops.loc[shops.category.eq("Магазины") & shops.medium_primary2002.map(true)].copy()
assert shops[KEY].is_unique and len(shops)==174
old174ids=set(shops[KEY])
assert len(old174ids)==174
singleton_summaries=[]
for sample,ids in [("lower338",set(candidates[KEY])),("old170_demography",old170ids),
                   ("old174_shops",old174ids)]:
 for view in ["publication","Jan1_candidate"]:
  centre_scope="old174_centre_units" if sample=="old174_shops" else "lower338"
  parent_scope="old174_parent_units" if sample=="old174_shops" else "lower338_parents"
  flagcols=[KEY,"same_singleton_all3_publications",
            "no_future_rows_affect_context","code_name_sets_unchanged_vs2020_2021"]
  centre=eligframe.loc[eligframe.scope.eq(centre_scope)
      & eligframe.view.eq(view) & eligframe[KEY].isin(ids),flagcols]
  parent=eligframe.loc[eligframe.scope.eq(parent_scope)
      & eligframe.view.eq(view) & eligframe[KEY].isin(ids),flagcols]
  g=centre.merge(parent,on=KEY,validate="one_to_one",suffixes=("_centre","_parent"))
  assert len(g)==len(ids),(sample,len(g),len(ids))
  g["same_singleton_all3_publications"]=g.same_singleton_all3_publications_centre
  g["no_future_rows_affect_context"]=(
      g.no_future_rows_affect_context_centre & g.no_future_rows_affect_context_parent)
  g["code_name_sets_unchanged_vs2020_2021"]=(
      g.code_name_sets_unchanged_vs2020_2021_centre
      & g.code_name_sets_unchanged_vs2020_2021_parent)
  singleton_summaries.append({"sample":sample,"view":view,
    "sample_n":len(ids),"tested_centres_n":len(g),
    "same_singleton_all3_n":int(g.same_singleton_all3_publications.sum()),
    "same_singleton_all3_no_future_rows_n":int((
       g.same_singleton_all3_publications & g.no_future_rows_affect_context).sum()),
    "unchanged_full_code_name_sets_n":int(g.code_name_sets_unchanged_vs2020_2021.sum()),
    "unresolved_n":int((~g.no_future_rows_affect_context).sum())})
# Nonshop main selection: separate publication-screen diagnostics only;
# these screens are code/name continuity checks, NEVER boundary verification.
panel=pd.read_csv(PANELDIR/"panels.csv")
p=panel.loc[panel.medium_primary2002.map(true)
            & panel.positive_other_population_all_years.map(true)].copy()
def number(v):
 return float(v) if pd.notna(v) else None
def stats(g):
 return {"centres_n":len(g),"regions_n":int(g.region_2021.nunique()),
  "shared_centres_n":int(g.upper_municipalities_n2020.gt(1).sum()),
  "own_decline_n":int(g.own_change2023_2025_pct.lt(0).sum()),
  "other_decline_n":int(g.other_change2023_2025_pct.lt(0).sum()),
  "share_increase_n":int(g.centre_share_change2023_2025_pp.gt(0).sum()),
  "median_own_change_pct":number(g.own_change2023_2025_pct.median()),
  "median_other_change_pct":number(g.other_change2023_2025_pct.median()),
  "median_share_change_pp":number(g.centre_share_change2023_2025_pp.median())}
sensitivity=[]
for view in ["publication","Jan1_candidate"]:
 screen=eligframe.loc[eligframe.scope.eq("upper1953") & eligframe.view.eq(view)]
 joined=p.merge(screen.drop(columns=["scope"]),on=KEY,validate="one_to_one")
 for restriction,mask in [
  ("baseline_conditional",pd.Series(True,index=joined.index)),
  ("same_code_sets_vs2020_2021",joined.code_sets_unchanged_vs2020_2021),
  ("same_code_name_sets_vs2020_2021",joined.code_name_sets_unchanged_vs2020_2021),
  ("same_code_name_sets_no_future_rows",joined.code_name_sets_unchanged_vs2020_2021
                                & joined.no_future_rows_affect_context)]:
  for strict in [False,True]:
   g=joined.loc[mask]
   if strict:
    g=g.loc[g.unchanged_observed_metadata.map(true)
            & g.publisher_no_transformation_flags.map(true)]
   sensitivity.append({"view":view,"restriction":restriction,
    "metadata_screen":strict,**stats(g)})
 joined.to_csv(OUT/("nonshop_panel_roster_flags_"+view+".csv"),index=False)
pd.DataFrame(sensitivity).to_csv(OUT/"nonshop_demography_roster_sensitivity.csv",index=False)

old_sensitivity=[]
old_medium=old170.loc[old170[KEY].isin(old170ids)].copy()
old_medium=old_medium.rename(columns={
 "own_growth_pct":"own_change2023_2025_pct",
 "other_growth_pct":"other_change2023_2025_pct",
 "share_change_pp":"centre_share_change2023_2025_pp",
})
old_medium["upper_municipalities_n2020"]=1
for view in ["publication","Jan1_candidate"]:
 lowerflags=eligframe.loc[eligframe.scope.eq("lower338") & eligframe.view.eq(view)]
 upperflags=eligframe.loc[eligframe.scope.eq("lower338_parents") & eligframe.view.eq(view)]
 flagcols=[KEY,"code_name_sets_unchanged_vs2020_2021","no_future_rows_affect_context"]
 g=old_medium.merge(lowerflags[flagcols],on=KEY,validate="one_to_one")
 g=g.merge(upperflags[flagcols],on=KEY,validate="one_to_one",suffixes=("_lower","_upper"))
 assert len(g)==len(old_medium)
 for restriction,mask in [
  ("baseline_conditional",pd.Series(True,index=g.index)),
  ("lower_and_parent_same_code_name_sets",
    g.code_name_sets_unchanged_vs2020_2021_lower & g.code_name_sets_unchanged_vs2020_2021_upper),
  ("lower_parent_same_code_name_sets_no_future_rows",
    g.code_name_sets_unchanged_vs2020_2021_lower & g.code_name_sets_unchanged_vs2020_2021_upper
    & g.no_future_rows_affect_context_lower & g.no_future_rows_affect_context_upper)]:
  old_sensitivity.append({"view":view,"restriction":restriction,**stats(g.loc[mask])})
pd.DataFrame(old_sensitivity).to_csv(OUT/"old170_demography_roster_sensitivity.csv",index=False)

summary={
 "scope":"full_publication_roster_continuity_not_boundary_verification",
 "raw_publication_inputs":inputs,
 "singleton_summary_code_name_continuity_requires_both_centre_and_parent":True,
 "old174_exact_definition":"internal_centre_district_common_panels2022_2024 category Магазины and medium_primary2002",
 "views":["publication","Jan1_candidate_with_previous_same_code_state_or_unresolved"],
 "Status_semantics_not_assumed":True,"future_rows_not_blindly_dropped":True,
 "publication_filename_not_effective_date":True,
 "Jan1_candidate_not_certified_Jan1_snapshot":True,
 "previous_state_substitution_does_not_resolve_temporal_ambiguity":True,
 "boundary_change_absence_established":False,
 "causal_effect_identified":False,"main_selection_modified":False,
 "future_rows_n":len(future_audit),
 "future_rows_previous_state_substitutions_n":sum(
    r["candidate_action"]=="previous_same_code_state" for r in future_audit),
 "future_rows_unresolved_n":sum(
    r["candidate_action"]!="previous_same_code_state" for r in future_audit),
 "scope_continuity":eligframe.groupby(["scope","view"]).agg(
    contexts_n=(KEY,"size"),
    unchanged_code_sets_n=("code_sets_unchanged_vs2020_2021","sum"),
    unchanged_code_name_sets_n=("code_name_sets_unchanged_vs2020_2021","sum"),
    no_future_rows_contexts_n=("no_future_rows_affect_context","sum")
 ).reset_index().to_dict("records"),
 "singleton_eligibility":singleton_summaries,
 "nonshop_demography_sensitivity":sensitivity,
 "old170_demography_sensitivity":old_sensitivity,
}
(OUT/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
print("FULL_ROSTER_ANALYSIS_BEGIN")
print(json.dumps(summary,ensure_ascii=False,separators=(",",":"),allow_nan=False))
print("FULL_ROSTER_ANALYSIS_END")
