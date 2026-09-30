"""Extract Rosstat Yearbook 2024 table 4.9 and prepare 2010–2021 bridge candidates.

Rounded thousand-person values are cross-source checks, never replacements for
census counts. This builder emits candidates only; it does not admit identity.
"""
from __future__ import annotations
import argparse, hashlib, json, re, shutil, tempfile
from pathlib import Path
import pandas as pd
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[2]
EVID=ROOT/"research_rebuild/evidence"
PDF=EVID/"discovery/official_sources_2010_2021_r2_yearbook/raw/rosstat_russian_statistical_yearbook_2024.pdf"
RECEIPT=PDF.parent.parent/"retrieval_receipt.json"
SELECTION=EVID/"releases/national_source_selection_r1_20260930"
SELECTED=SELECTION/"selected_observations.parquet"
OUT_ID="yearbook_table49_2010_2021_candidates_r2_20260930"
PDF_SHA="bac43b438869d7b11ca595acd121726833d2bf2e54004351db825cade4c29da7"
SELECTED_SHA="dd8d437c1a1f5cebf2b45c55e7a6e2015f3c1a295cade827a71bb76189a485df"
RELEASE_SHA="37b4bf695087032e13baac88e7c432849bf3aa4543e40bcd2a5df6e8429242f6"
SOURCE_FILE_PINS={
 "data/raw/2010_official_tom1/tom-1-chislennost-i-razmeshchenie-naseleniya.pdf":"42cb939d8024042ffcf8a708676cef3f159a93e4dad697086c80465d445887c3",
 "data/raw/2010_official_tom11/pub-11-1-4.pdf":"db2528e6db3c6089351bd09d253c9dfa607e2f2dff6cc45d1174fb21fa96d500",
 "data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet":"86c197cd522e0b63669e9c6e7f43fd3d82b3704c6a126c800a9968ecd16cae14",
}
HEADERS=["2002","2010","2021","2022","2023","2024"]

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def norm(v):
 s="" if pd.isna(v) else str(v).casefold().replace("ё","е").replace("ѐ","е")
 s=re.sub(r"[«»\"'`()\[\]{}.,;:№/\\–—-]"," ",s)
 return re.sub(r"\s+"," ",s).strip()
def norm_region(v):
 s=norm(v)
 words=[x for x in s.split() if x not in {"республика","область","край","автономная","автономный","округ","ао","респ","обл","кр","город","федерального","значения"}]
 return " ".join(words)
def parse_num(s):
 if not s: return None
 if s=="…": return None
 return int(s.replace(" ",""))
def cells_from_line(line): return re.split(r"\s{2,}",line.strip())
def parse_rows(reader):
 rows=[]; pending=None
 for pidx in (90,91,92):
  text=reader.pages[pidx].extract_text(extraction_mode="layout") or ""
  for lineno,line in enumerate(text.splitlines(),1):
   parts=cells_from_line(line)
   if len(parts)==2 and re.search(r"[А-Яа-яЁё]",parts[0]) and not re.fullmatch(r"\d+\..*",parts[0]):
    pending={"name":parts[0],"english":parts[1],"page":pidx+1,"line":lineno,"raw":line}
    continue
   if len(parts) not in (6,8): continue
   if not re.search(r"[А-Яа-яЁё]",parts[0]): continue
   if not all(re.fullmatch(r"(?:\d[\d ]*|…)",x) for x in parts[1:-1]): continue
   if len(parts)==8:
    name=parts[0]; vals=parts[1:7]; english=parts[7]
    pstart=pidx+1; lstart=lineno; raw=line
   else:
    # Two blank census cells are visibly present in the original table for
    # Zelenodolsk and Khanty-Mansiysk; they are not zero-population values.
    name=parts[0]; vals=["","",*parts[1:5]]; english=parts[5]
    pstart=pidx+1; lstart=lineno; raw=line
   if vals and pending and parts[0].startswith("("):
    name=pending["name"]+" "+parts[0]
    english=pending["english"]+" "+english
    pstart=pending["page"]; lstart=pending["line"]
    raw=pending["raw"]+"\n"+line
    pending=None
   # superscript footnote markers occur as literal digit-parenthesis suffixes.
   marks=re.findall(r"(?<!\d)([1-9])\)",name)
   clean=re.sub(r"([1-9])\)","",name).strip()
   qual=None
   qm=re.search(r"\(([^()]*(?:область|край|республика)[^()]*)\)",clean,flags=re.I)
   if qm: qual=qm.group(1); clean=(clean[:qm.start()]+clean[qm.end():]).strip()
   values={h:{"raw":v,"thousand":parse_num(v),"missing_kind":("ellipsis" if v=="…" else "blank" if not v else None)} for h,v in zip(HEADERS,vals)}
   rows.append({"row_id":f"ROSSTAT2024:YB4.9:pdf_page_{pidx+1}:line_{lineno}","pdf_page_1based":pstart,"printed_page":pstart-1,
    "page_line_start_1based":lstart,"data_line_page_1based":pidx+1,"data_line_1based":lineno,
    "raw_russian_label":name,"normalized_city_label":clean,"explicit_region_qualifier_raw":qual,"explicit_region_qualifier_key":norm_region(qual) if qual else None,
    "footnote_markers":";".join(marks),"english_label_raw":english,"raw_table_line":raw,
    **{f"{h}_raw":values[h]["raw"] for h in HEADERS},**{f"{h}_thousand":values[h]["thousand"] for h in HEADERS},
    **{f"{h}_missing_kind":values[h]["missing_kind"] for h in HEADERS}})
   pending=None
 return rows

def bind_candidates(rows,selected):
 # Exact city-name/type index; region qualifier only narrows, never fuzzy-matches.
 sel=selected.copy(); sel["_name_key"]=sel.settlement_name.map(norm); sel["_type_key"]=sel.settlement_type.map(norm); sel["_region_key"]=sel.region_raw.map(norm_region)
 city=sel[sel._type_key.eq("город")]
 indexes={y:{} for y in (2002,2010,2021)}
 for y in indexes:
  yy=city[city.census_year.eq(y)]
  for key,g in yy.groupby("_name_key",sort=False): indexes[y][key]=g
 output=[]
 federal={"москва","санкт петербург","севастополь"}
 for row in rows:
  key=norm(row["normalized_city_label"]); qual=row["explicit_region_qualifier_key"]
  item=dict(row); peryear={}
  for y in (2002,2010,2021):
   g=indexes[y].get(key,city.iloc[0:0])
   if len(g) and qual: g=g[g._region_key.eq(qual)]
   # For an unqualified label, a same-name city in more than one region is
   # ambiguous and remains so; no administrative-context guess is substituted.
   ids=[]
   if len(g)==1:
    r=g.iloc[0]; ids=[r]
   pop_th=row[f"{y}_thousand"]
   rec={"match_count":int(len(g)),"source_record_id":None,"source_file":None,"source_sha256":None,
        "source_sheet":None,"source_row":None,"source_native_id":None,"source_locator":None,
        "region_raw":None,"settlement_type":None,"population":None,"rounding_compatible":None}
   if len(g)==1:
    r=g.iloc[0]
    rec.update({"source_record_id":str(r.source_record_id),"source_file":None if pd.isna(r.source_file) else str(r.source_file),
      "source_sha256":None if pd.isna(r.source_sha256) else str(r.source_sha256),"source_sheet":None if pd.isna(r.source_sheet) else str(r.source_sheet),
      "source_row":None if pd.isna(r.source_row) else int(r.source_row),"source_native_id":None if pd.isna(r.source_native_id) else str(r.source_native_id),
      "source_locator":None if pd.isna(r.source_locator) else str(r.source_locator),"region_raw":str(r.region_raw),
      "settlement_type":str(r.settlement_type),"population":None if pd.isna(r.population) else int(r.population)})
    rel=str(r.source_file) if not pd.isna(r.source_file) else None
    if rel and (ROOT/rel).is_file():
     actual=sha(ROOT/rel)
     if rel in SOURCE_FILE_PINS and actual!=SOURCE_FILE_PINS[rel]: raise ValueError(f"endpoint source file changed: {rel}")
     rec["source_sha256"]=actual
    if pop_th is not None and rec["population"] is not None:
     rec["rounding_compatible"]=(pop_th*1000-500 <= rec["population"] < pop_th*1000+500)
   peryear[y]=rec
   for k,v in rec.items(): item[f"{y}_{k}"]=v
  statuses=[]
  if key in federal: statuses.append("federal_city_scope_hold")
  if "2" in row["footnote_markers"].split(";") or "3" in row["footnote_markers"].split(";"): statuses.append("boundary_change_footnote_hold")
  for y in (2010,2021):
   if row[f"{y}_missing_kind"]: statuses.append(f"yearbook_{y}_value_{row[f'{y}_missing_kind']}")
   if peryear[y]["match_count"]!=1: statuses.append(f"{y}_endpoint_not_unique")
   elif peryear[y]["rounding_compatible"] is False: statuses.append(f"{y}_value_outside_rounded_interval")
  a,b=peryear[2010],peryear[2021]
  if a["match_count"]==b["match_count"]==1 and a["region_raw"] and b["region_raw"] and norm_region(a["region_raw"])!=norm_region(b["region_raw"]): statuses.append("region_changed_or_binding_conflict")
  # Historical 2002 availability is independent of the 2010-2021 proposal.
  if row["2002_missing_kind"]: item["2002_source_status"]="source_ellipsis_or_blank_not_zero"
  elif peryear[2002]["match_count"]==0: item["2002_source_status"]="no_unique_selected_2002_city_endpoint"
  elif peryear[2002]["match_count"]>1: item["2002_source_status"]="ambiguous_selected_2002_city_endpoint"
  elif peryear[2002]["rounding_compatible"] is False: item["2002_source_status"]="selected_2002_population_outside_rounded_interval"
  else: item["2002_source_status"]="rounded_value_matches_selected_city_endpoint"
  item["candidate_status_2010_2021"]="candidate_for_independent_review" if not statuses else ";".join(sorted(set(statuses)))
  item["is_identity_admission"]=False
  item["candidate_method_note"]="Official yearbook row publishes both 2010 and 2021 census values rounded to 1,000; exact selected endpoints bound independently by city name, city type, region where printed, and rounding interval. Candidate only; no automatic identity admission."
  output.append(item)
 return output

def build(output:Path):
 output=output.resolve()
 output.parent.mkdir(parents=True,exist_ok=True)
 if output.exists(): raise FileExistsError(output)
 for p,h in ((PDF,PDF_SHA),(SELECTED,SELECTED_SHA),(SELECTION/"release_manifest.json",RELEASE_SHA),*[(ROOT/k,v) for k,v in SOURCE_FILE_PINS.items()]):
  if not p.is_file() or sha(p)!=h: raise ValueError(f"required frozen input missing/changed: {p}")
 receipt=json.loads(RECEIPT.read_text(encoding="utf-8"))
 reader=PdfReader(str(PDF)); rows=parse_rows(reader)
 if len(rows)!=172: raise ValueError(f"expected 172 table rows, extracted {len(rows)}")
 if len({r["row_id"] for r in rows})!=len(rows): raise ValueError("duplicate table source row IDs")
 selected=pd.read_parquet(SELECTED)
 candidates=bind_candidates(rows,selected)
 out=Path(tempfile.mkdtemp(prefix=f".{OUT_ID}.stage-",dir=output.parent))
 rawdir=out/"raw_pages";rawdir.mkdir()
 page_text=[]
 for pidx in (90,91,92):
  txt=reader.pages[pidx].extract_text(extraction_mode="layout") or ""
  (rawdir/f"pdf_page_{pidx+1}.txt").write_text(txt,encoding="utf-8")
  page_text.append({"pdf_page_1based":pidx+1,"printed_page":pidx,"line_count":len(txt.splitlines()),"raw_text_sha256":sha(rawdir/f"pdf_page_{pidx+1}.txt")})
 pd.DataFrame(rows).to_csv(out/"table49_source_rows.csv",index=False)
 pd.DataFrame(candidates).to_csv(out/"bridge_candidates_2010_2021.csv",index=False)
 footnotes={"table_title":"Cities with population 100 000 and over", "unit":"thousand persons", "census_dates":{"2002":"2002-10-09","2010":"2010-10-14","2021":"2021-10-01"},
  "noncensus_columns":{"2022":"estimate as of January 1","2023":"estimate as of January 1","2024":"estimate as of January 1"},
  "notes":[{"marker":"1","text":"2002, 2010, 2021 are census values at dates above; remaining columns are Jan 1 estimates."},
   {"marker":"2","text":"Balashikha values account for its 2015 boundary change under Moscow Oblast law 208/2014-OZ and amendments."},
   {"marker":"3","text":"Moscow values account for boundary change effective 2012-07-01 under Federation Council resolution 560-SF."}],
  "limitations":["Rounded thousand-person values can support continuity only when exact source observations independently bind; they are not exact population replacement values.","Ellipsis and blank cells are preserved as distinct missing-value states, never converted to zero.","Federal cities and rows with boundary-change footnotes are held for separate review.","This is a candidate artifact, not an accepted identity release."]}
 page93=reader.pages[92].extract_text(extraction_mode="layout") or ""
 lines93=page93.splitlines()
 start=next(i for i,line in enumerate(lines93) if "Данные  приведены" in line or "Данные приведены" in line)
 stop=next(i for i,line in enumerate(lines93) if line.lstrip().startswith("1) Data"))
 footnotes["source_verbatim_russian_footnote_block"]="\n".join(lines93[start:stop]).rstrip()
 footnotes["source_verbatim_english_footnote_block"]="\n".join(lines93[stop:]).split("Российский статистический ежегодник")[0].rstrip()
 (out/"table49_method_notes.json").write_text(json.dumps(footnotes,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 status=pd.Series([x["candidate_status_2010_2021"] for x in candidates]).value_counts().to_dict()
 manifest={"release_id":OUT_ID,"status":"candidate_only_not_admitted","source_pdf":{"path":str(PDF.relative_to(ROOT)),"sha256":PDF_SHA,"bytes":PDF.stat().st_size,"retrieval_receipt_sha256":sha(RECEIPT),"retrieval_receipt":receipt,
  "table_pages":page_text,"table4_9_pdf_locator":"PDF pages 91-93; printed pages 90-92; page line numbers are 1-based pypdf layout extraction lines"},
  "selection_input":{"release_manifest_sha256":RELEASE_SHA,"selected_observations_sha256":SELECTED_SHA},
  "endpoint_source_files":{k:{"sha256":v,"bytes":(ROOT/k).stat().st_size} for k,v in SOURCE_FILE_PINS.items()},
  "extraction":{"method":"pypdf extract_text(layout), split on repeated column whitespace; two explicitly blank 2002/2010 cells preserved for Zelenodolsk and Khanty-Mansiysk; wrapped Blagoveshchensk label joins next-line region qualifier","row_count":len(rows),"page_row_counts":{str(p):sum(r["pdf_page_1based"]==p for r in rows) for p in (91,92,93)}},
  "candidate_metrics":{"rows":len(candidates),"status_counts":status,"candidate_rows":sum(x["candidate_status_2010_2021"]=="candidate_for_independent_review" for x in candidates),
   "candidate_population_mass_2010":int(sum((x.get("2010_population") or 0) for x in candidates if x["candidate_status_2010_2021"]=="candidate_for_independent_review")),
   "candidate_population_mass_2021":int(sum((x.get("2021_population") or 0) for x in candidates if x["candidate_status_2010_2021"]=="candidate_for_independent_review"))},
  "builder_sha256":sha(Path(__file__).resolve()),"outputs":{}}
 for p in sorted(out.rglob("*")):
  if p.is_file(): manifest["outputs"][p.relative_to(out).as_posix()]={"sha256":sha(p),"bytes":p.stat().st_size}
 (out/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 out.rename(output)
 return manifest
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--output",type=Path,required=True);a=p.parse_args();print(json.dumps(build(a.output),ensure_ascii=False,indent=2))
