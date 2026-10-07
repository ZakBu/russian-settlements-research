"""Admit exact, unique county/name continuity with explicit source type variants."""
import json
import pandas as pd

from current_chain_state_20261007 import normalize, distance_km, sha
from apply_unique_county_name_bridge_20261007 import county_key
from working_state_20261007 import load, E

REVIEW=E/"county_type_change_batch_20261007"
OUT=E/"county_type_change_application_20261007"


def main():
    state=load(stage=5)
    before=state.metrics()
    candidates=pd.read_csv(REVIEW/"candidate_identity_edge_delta.csv",keep_default_na=False)
    sample=pd.read_csv(REVIEW/"sampled_raw_source_checks.csv",keep_default_na=False)
    verified=json.loads((REVIEW/"structural_verification.json").read_text())
    obs=state.obs[state.obs.is_additive_settlement_record.fillna(False)].copy()
    obs=obs[~obs.settlement_name.fillna("").str.contains(r"\(часть",regex=True)]
    obs["n"]=obs.name_norm.map(normalize)
    obs["r"]=obs.region_norm.map(normalize)
    obs["d"]=obs.district_raw.map(county_key)
    counts=obs.groupby(["census_year","n","r","d"]).size().to_dict()
    edges,held=[],[]
    for row in candidates.to_dict("records"):
        a,b=row["from_source_record_id"],row["to_source_record_id"]
        ar,br=state.by_id.loc[a],state.by_id.loc[b]
        key=(normalize(ar.name_norm),normalize(ar.region_norm),county_key(ar.district_raw))
        if key!=(normalize(br.name_norm),normalize(br.region_norm),county_key(br.district_raw)) or not key[0] or not key[2]:
            raise ValueError("County/name identity key changed")
        if any(counts.get((int(r.census_year),*key),0)!=1 for r in (ar,br)):
            raise ValueError("Name is not unique in county without using type")
        if state.uf.find(a)==state.uf.find(b):
            held.append({"from_source_record_id":a,"to_source_record_id":b,"reason":"already_connected"})
            continue
        donor_id=row["point_donor_source_record_id"]
        donor=state.point_rows[donor_id]
        for sid in (a,b):
            point=state.point_rows.get(sid)
            if sid in state.conflicting_point_targets or (point and distance_km((point["latitude"],point["longitude"]),(donor["latitude"],donor["longitude"]))>5):
                raise ValueError("Contradictory accepted geometry")
        state.union(a,b)
        row["decision_status"]="checked_rule_accepted"
        row["type_variation_is_dated_legal_event"]=False
        edges.append(row)
    points=pd.read_csv(REVIEW/"candidate_point_use_delta.csv",keep_default_na=False)
    accepted=[]
    for row in points.to_dict("records"):
        sid,donor_id=row["target_source_record_id"],row["coordinate_source_record_id"]
        if sid in state.point_rows:
            continue
        if state.uf.find(sid)!=state.uf.find(donor_id):
            raise ValueError("Point transfer is not over an accepted identity")
        donor=state.point_rows[donor_id]
        if distance_km((float(row["latitude"]),float(row["longitude"])),(donor["latitude"],donor["longitude"]))>.000001:
            raise ValueError("Transferred point differs from donor")
        row["coordinate_admission_status"]="reviewed_extension_rule_accepted"
        accepted.append(row)
        state.point_rows[sid]=dict(row,latitude=float(row["latitude"]),longitude=float(row["longitude"]),point_ledger_path=str(OUT/"accepted_point_use_delta.csv"))
    OUT.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(edges).to_csv(OUT/"accepted_identity_edge_delta.csv",index=False)
    pd.DataFrame(accepted).to_csv(OUT/"accepted_point_use_delta.csv",index=False)
    pd.DataFrame(held,columns=["from_source_record_id","to_source_record_id","reason"]).to_csv(OUT/"held_pairs.csv",index=False)
    after=state.metrics()
    receipt={"status":"applied_unique_explicit_county_name_rule_with_printed_type_variants","new_edges":len(edges),"new_point_uses":len(accepted),"candidate_author_raw_sample_endpoints":len(sample),"independent_root_structural_replay":True,"baseline":before,"after":after,"population_gain":{y:after[y]["covered_population"]-before[y]["covered_population"] for y in before},"historical_legal_type_change_asserted":False,"source_population_values_modified":False,"boundary_comparability_asserted":False,"inputs":{str(p):sha(p) for p in state.inputs+list(REVIEW.glob("*.csv"))+list(REVIEW.glob("*.json"))},"outputs":{p.name:sha(p) for p in OUT.glob("*.csv")}}
    (OUT/"application_receipt.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n")
    (OUT/"README.md").write_text("# Различия напечатанного типа\n\nПринято по уникальному имени в одном явно указанном районе и регионе без использования типа для искусственного устранения омонимов. Есть принятая точка компонента; две имеющиеся точки не противоречат друг другу. Противоречия исходных координат, коллизии, части НП, административные итоги, события и повтор года проверены при генерации. Root повторил уникальность, слияния и происхождение переносимых точек; автор кандидатов проверил 80 исходных строк (top5 + random35 seed20261007). Это ограниченная проверка, не калиброванная оценка всей базы. Различия типов источников не объявлены доказанными юридическими преобразованиями. Население и границы не гармонизированы.\n")
    print(json.dumps({k:receipt[k] for k in ("new_edges","new_point_uses","population_gain","after")},ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
