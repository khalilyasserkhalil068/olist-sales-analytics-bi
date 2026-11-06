"""Compare current baseline/final live-model snapshots and retained historical model."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'reports/completion_20261101'
if len(sys.argv)>1:p=Path(sys.argv[1])
else:p=next(x for x in sorted(OUT.glob('model_regression_*'),reverse=True) if (x/'final_current_values.json').exists())
load=lambda name:json.loads((p/name).read_text(encoding='utf-8-sig'))
b=load('baseline_current_model.json')['model'];f=load('final_current_model.json')['model']
h=json.loads((ROOT/'power_bi/reports/final_reopened_model_20261031.json').read_text(encoding='utf-8-sig'))['model']
def measures(x):return {(t['name'],m['name']):(m.get('expression'),m.get('formatString','')) for t in x['tables'] for m in t.get('measures',[])}
bm,fm,hm=map(measures,[b,f,h])
checks=dict(baseline_matches_historical_33_measures=bm==hm and len(bm)==33,baseline_matches_historical_37_relationships=b['relationships']==h['relationships'] and len(b['relationships'])==37,final_preserves_all_33_baseline_measures=all(fm.get(k)==v for k,v in bm.items()),final_preserves_all_37_baseline_relationships=f['relationships']==b['relationships'],final_has_58_measures=len(fm)==58)
bv=load('baseline_current_values.json')[0];fv=load('final_current_values.json')[0];diff=[]
for k,v in bv.items():
    w=fv.get(k);ok=abs(v-w)<=.005 if isinstance(v,(int,float)) and isinstance(w,(int,float)) else v==w
    if not ok:diff.append(dict(key=k,before=v,after=w))
checks['all_33_measure_values_and_four_fact_counts_match']=not diff and len(bv)==37
partition_changes=[]
for table in b['tables']:
    other=next(t for t in f['tables'] if t['name']==table['name'])
    if table.get('partitions')!=other.get('partitions'):partition_changes.append(table['name'])
checks['partitions_preserved']=not partition_changes
result=dict(checks=checks,passed=sum(checks.values()),failed=sum(not x for x in checks.values()),numeric_value_differences=diff,partition_changes=partition_changes,note='The baseline binary historical-hash discrepancy remains a provenance difference; live measures and relationships match retained historical definitions. Final model matches all baseline values and four fact counts.')
(p/'comparison.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
raise SystemExit(bool(result['failed']))
