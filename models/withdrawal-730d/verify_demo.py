"""Exercise the predeclared synthetic forward and inverse interfaces."""
from pathlib import Path
import algorithm as m
import joblib,json,sys,numpy as np,pandas as pd
root=Path(__file__).resolve().parent;out=root/'synthetic_results';p=out/'models.joblib'
# Re-home trusted locally generated classes so consumers can import the module.
sys.modules['__main__'].IntervalHazards=m.IntervalHazards;sys.modules['__main__'].CoxHazards=m.CoxHazards
bundle=joblib.load(p);joblib.dump(bundle,p)
audit=json.loads((out/'审计.json').read_text('utf-8'));audit['model_sha256']=m.sha(p);m.save(out/'审计.json',audit)
proto,df,x,_,t,c=m.load(root/'synthetic_input/ten_interfaces')
assert len(df)==10 and proto['origin']=='SYNTHETIC_DEMO'
m.save(out/'十例接口核验.json',dict(origin=proto['origin'],patient_count=10,valid_links=10,early_censored=int(((c==0)&(t<730)).sum()),unknown_fields=int(x.isna().sum().sum())))
vals=dict(zip(m.FIELDS,[4.,48.,12.,0.,8.,0.,0.,None]))
query=dict(mode='existing',age_at_index=30.,interval=[.15,.45],fixed=vals,unknown_fields=['eeg_epileptiform'],axes={'eeg_epileptiform':[0.,1.]},budget=16)
m.save(root/'查询示例.json',query);ans=m.search(bundle,query);m.save(out/'逆向候选.json',ans)
for r in ans['hits']+ans['nearest']:
    assert np.isclose(m.forward(bundle,r['values'])[0],r['risk']) and all(r['values'][k]==v for k,v in vals.items() if v is not None)
m.save(out/'无命中示例.json',m.search(bundle,dict(query,interval=[.999,1.])))
try:m.search(bundle,dict(query,axes={'medication_dose':[0,1]}))
except ValueError:pass
else:raise AssertionError('Drug/dose axis must be rejected')
baseline={**vals,'eeg_epileptiform':0.};v,dist=m.forward(bundle,baseline);m.save(root/'正向示例.json',baseline)
m.save(out/'固定验收病例.json',dict(origin=proto['origin'],input=baseline,risk_730=v,training_k3_distance=dist,status='SYNTHETIC_INTERFACE_ONLY',model_sha256=m.sha(p)))
cal=pd.read_csv(out/'校准.csv');svg=['<svg xmlns="http://www.w3.org/2000/svg" width="620" height="390"><rect width="100%" height="100%" fill="white"/><text x="55" y="30">Synthetic fixture | 730-day calibration</text><path d="M65 55 V320 H560 M65 320 L560 55" fill="none" stroke="#9aa7ae"/>']
for model,color in [('interval','#176b75'),('cox','#b55b2d')]:
    z=cal[(cal.model==model)&(cal.branch=='structured_and_verified_text')]
    for r in z.itertuples():svg.append(f'<circle cx="{65+495*r.mean_risk:.1f}" cy="{320-265*r.observed_ipcw:.1f}" r="5" fill="{color}"/>')
svg+=['<text x="170" y="356">Predicted 730-day risk (0–1)</text><text x="65" y="379">Teal: interval | Orange: Cox | Observed: IPCW recurrence fraction</text></svg>']
(out/'校准图.svg').write_text(''.join(svg),'utf-8')
print('TEN_INTERFACES_PASS',ans['status'],len(ans['hits']),'negative test PASS')
