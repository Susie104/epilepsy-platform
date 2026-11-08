"""Research module for 730-day seizure recurrence after first actual dose reduction."""
from pathlib import Path
import argparse,datetime,hashlib,itertools,json,os,time
import numpy as np,pandas as pd,joblib
from scipy.optimize import minimize
from scipy.special import logsumexp
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.linear_model import PoissonRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score

FIELDS=['epilepsy_duration_before_remission_years','seizure_free_months','age_at_onset','febrile_seizure_history','seizure_count_before_remission','self_limiting_syndrome','developmental_delay','eeg_epileptiform']
BINARY=[3,5,6,7];ENDS=np.array([90.,180.,365.,545.,730.]);HORIZON=730.
def save(p,obj):p.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False),'utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def demo_inputs(root):
    if root.exists() and any(root.iterdir()):raise ValueError('Use a fresh empty demo input directory; existing data preserved.')
    root.mkdir(parents=True,exist_ok=True);rng=np.random.default_rng(730);co=[];ob=[];fields=[]
    for i in range(260):
        pid=f'DEMO-{i:04d}';eid=pid+'-E1';idx=pd.Timestamp('2020-01-01')+pd.Timedelta(days=int(rng.integers(800)))
        v=[rng.uniform(.25,12),rng.uniform(12,100),rng.uniform(1,52),rng.binomial(1,.2),rng.integers(1,36),rng.binomial(1,.3),rng.binomial(1,.13),rng.binomial(1,.28)]
        age=float(v[2]+v[0]+v[1]/12+rng.uniform(0,8))
        co.append([pid,eid,idx.date(),round(age,2),'approved','SYNTHETIC_DEMO'])
        # Artificial data generator only. Coefficients have no clinical interpretation.
        rate=.0006*np.exp(.04*v[0]-.013*(v[1]-36)+.6*v[7]+.45*v[6]-.5*v[5])
        rec=int(rng.exponential(1/rate))+1;death=int(rng.exponential(4100))+1
        censor=int(rng.uniform(90,1200));end=min(rec,death,censor);date=(idx+pd.Timedelta(days=end)).date()
        ob.append([pid,eid,date if end==rec else '',date if end==death and end!=rec else '',date,'approved'])
        for j,(name,value) in enumerate(zip(FIELDS,v)):
            unknown=rng.random()<.10
            fields.append([pid,eid,name,'' if unknown else round(float(value),4),'unknown' if unknown else 'known','verified_text' if j in (3,5,7) and i%3==0 else 'structured',(idx-pd.Timedelta(days=1)).date(),'TEACHING-'+str(i),'approved'])
    tabs=dict(cohort=pd.DataFrame(co,columns=['patient_id','episode_id','index_date','age_at_index','review_status','origin']),outcomes=pd.DataFrame(ob,columns=['patient_id','episode_id','recurrence_date','death_date','last_followup_date','review_status']),baseline_fields=pd.DataFrame(fields,columns=['patient_id','episode_id','field','value','state','source_kind','available_date','source_doc_id','review_status']))
    for n,df in tabs.items():df.to_csv(root/(n+'.csv'),index=False,encoding='utf-8-sig')
    save(root/'protocol.json',dict(origin='SYNTHETIC_DEMO',approval='teaching_fixture',death_policy='competing',index='first actual dose reduction',horizon=730,endpoint='first adjudicated recurrence',patient_per_episode='first eligible episode only'))
    demo10=root/'ten_interfaces';demo10.mkdir(exist_ok=True)
    for n,df in tabs.items():df[df.patient_id.isin(tabs['cohort'].patient_id.iloc[:10])].to_csv(demo10/(n+'.csv'),index=False,encoding='utf-8-sig')
    save(demo10/'protocol.json',json.loads((root/'protocol.json').read_text('utf-8')))
def load(root):
    proto=json.loads((root/'protocol.json').read_text('utf-8-sig'))
    if proto.get('origin') not in ('SYNTHETIC_DEMO','DEIDENTIFIED_APPROVED') or proto.get('death_policy')!='competing' or proto.get('horizon')!=730:raise ValueError('Origin, 730-day endpoint and competing-death policy must be declared')
    if proto['origin']!='SYNTHETIC_DEMO' and (proto.get('approval')!='clinician_approved' or not all(proto.get(k) for k in ['population','index','endpoint','approval_id'])):raise ValueError('Real cohort needs reviewed definitions and approval identifier')
    c,o,b=[pd.read_csv(root/(n+'.csv'),dtype={'patient_id':str,'episode_id':str}) for n in ['cohort','outcomes','baseline_fields']]
    if c.patient_id.isna().any() or c.patient_id.duplicated().any() or c.episode_id.duplicated().any():raise ValueError('Require one first eligible episode per distinct patient')
    key=['patient_id','episode_id']
    if set(map(tuple,c[key].to_numpy()))!=set(map(tuple,o[key].to_numpy())):raise ValueError('Outcome keys do not match cohort')
    if not set(map(tuple,b[key].to_numpy()))<=set(map(tuple,c[key].to_numpy())):raise ValueError('Orphan baseline')
    if (c.origin!=proto['origin']).any() or not (c.review_status.eq('approved').all() and o.review_status.eq('approved').all()):raise ValueError('Review or origin pending')
    d=c.merge(o,on=key,validate='one_to_one').set_index('patient_id')
    for name in ['index_date','recurrence_date','death_date','last_followup_date']:d[name]=pd.to_datetime(d[name],errors='raise')
    if d[['index_date','last_followup_date']].isna().any().any():raise ValueError('Missing index or last follow-up')
    for name in ['recurrence_date','death_date']:
        if ((d[name]<=d.index_date)|(d[name]>d.last_followup_date)).any():raise ValueError('Event date outside observed interval')
    if (d.recurrence_date==d.death_date).any() or (d.recurrence_date>d.death_date).any():raise ValueError('Death/recurrence sequence requires adjudication')
    end=d[['recurrence_date','death_date','last_followup_date']].min(axis=1)
    t=(end-d.index_date).dt.days.to_numpy(dtype=float)
    if np.any(t<=0):raise ValueError('Zero or negative observation')
    cause=np.where(d.recurrence_date==end,1,np.where(d.death_date==end,2,0));cause=np.where(t>730,0,cause);t=np.minimum(t,730)
    x=pd.DataFrame(np.nan,index=d.index,columns=FIELDS);s=x.copy()
    if b.duplicated(['patient_id','episode_id','field']).any():raise ValueError('Multiple unresolved versions of a baseline field')
    for r in b.itertuples():
        if r.field not in FIELDS or r.review_status!='approved':raise ValueError('Unexpected or unreviewed baseline field')
        date=pd.to_datetime(r.available_date);idx=d.loc[r.patient_id,'index_date']
        if pd.isna(date) or date>idx:raise ValueError('Predictor unavailable at index')
        if r.source_kind not in ('structured','verified_text') or pd.isna(r.source_doc_id):raise ValueError('Provenance missing')
        if r.state=='unknown':
            if pd.notna(r.value):raise ValueError('Unknown state with supplied value')
            continue
        if r.state!='known' or pd.isna(r.value) or not np.isfinite(r.value) or r.value<0:raise ValueError('Invalid known value')
        if FIELDS.index(r.field) in BINARY and r.value not in (0,1):raise ValueError('Binary value outside {0,1}')
        if r.field=='seizure_count_before_remission' and r.value!=int(r.value):raise ValueError('Observed exact count must be integral')
        x.loc[r.patient_id,r.field]=r.value
        if r.source_kind=='structured':s.loc[r.patient_id,r.field]=r.value
    if (x.age_at_onset+x.epilepsy_duration_before_remission_years+x.seizure_free_months/12>d.age_at_index+.1).any():raise ValueError('Inconsistent timeline or units')
    return proto,d,x,s,t,cause
class IntervalHazards:
    def fit(self,x,t,c):
        design=[];labels=[];exposures=[]
        for j,(lo,hi) in enumerate(zip(np.r_[0,ENDS[:-1]],ENDS)):
            idx=t>lo;days=(np.minimum(t[idx],hi)-lo)/365.
            design.append(np.c_[x[idx],np.tile(np.eye(len(ENDS))[j],(idx.sum(),1))])
            labels.append(np.c_[((c[idx]==1)&(t[idx]<=hi))/days,((c[idx]==2)&(t[idx]<=hi))/days]);exposures.extend(days)
        a=np.vstack(design);y=np.vstack(labels)
        self.models=[PoissonRegressor(alpha=.08,max_iter=400).fit(a,y[:,j],sample_weight=exposures) for j in range(2)];return self
    def risk(self,x):
        surv=np.ones(len(x));cif=np.zeros(len(x))
        for j,(lo,hi) in enumerate(zip(np.r_[0,ENDS[:-1]],ENDS)):
            a=np.c_[x,np.tile(np.eye(len(ENDS))[j],(len(x),1))]
            h1,h2=[m.predict(a) for m in self.models];total=h1+h2;prob=-np.expm1(-total*(hi-lo)/365)
            cif+=surv*prob*h1/total;surv*=1-prob
        return cif
class CoxHazards:
    def fit(self,x,t,c):
        self.components=[]
        for event in (1,2):
            ts=np.unique(t[c==event]);risk=[np.flatnonzero(t>=v) for v in ts];who=[np.flatnonzero((t==v)&(c==event)) for v in ts]
            def objective(beta):
                v=x@beta;loss=.5*float(beta@beta);g=beta.copy()
                for ri,di in zip(risk,who):
                    lse=logsumexp(v[ri]);w=np.exp(v[ri]-lse);loss+=len(di)*lse-v[di].sum();g+=len(di)*(w@x[ri])-x[di].sum(axis=0)
                return loss,g
            opt=minimize(objective,np.zeros(x.shape[1]),jac=True,method='L-BFGS-B')
            if not opt.success:raise ValueError('Cox optimization failed: '+opt.message)
            beta=opt.x;hazard={v:len(di)*np.exp(-logsumexp(x[ri]@beta)) for v,ri,di in zip(ts,risk,who)}
            self.components.append((beta,hazard))
        return self
    def risk(self,x):
        co=self.components;times=sorted(set(co[0][1])|set(co[1][1]));s=np.ones(len(x));risk=np.zeros(len(x));weights=[np.exp(x@b) for b,_ in co]
        for t in times:
            h1=weights[0]*co[0][1].get(t,0);h2=weights[1]*co[1][1].get(t,0);h=h1+h2
            risk+=s*(-np.expm1(-h))*np.divide(h1,h,out=np.zeros_like(h1),where=h>0);s*=np.exp(-h)
        return risk
def censor_weights(train_t,train_c,t,c):
    ts=np.unique(train_t[(train_c==0)&(train_t<730)]);g=1.;surv=[]
    for day in ts:g*=1-np.sum((train_t==day)&(train_c==0))/np.sum(train_t>=day);surv.append(g)
    def G(day,left):
        i=np.searchsorted(ts,day,side='left' if left else 'right')-1;return 1. if i<0 else surv[i]
    w=np.zeros(len(t))
    for i in range(len(t)):
        if c[i]!=0:pr=G(t[i],True)
        elif t[i]>=730:pr=G(730,False)
        else:continue
        if pr<.05:raise ValueError('Censoring support insufficient at requested horizon')
        w[i]=1/pr
    return w
def scores(y,p,w):
    ok=w>0
    auc=float(roc_auc_score(y[ok],p[ok],sample_weight=w[ok])) if len(np.unique(y[ok]))==2 else None
    return dict(auc_730=auc,brier_730=float(np.mean(w*(y-p)**2)),known_weighted=int(ok.sum()))
def fit(root,out):
    if out.exists() and any(out.iterdir()):raise ValueError('Use a fresh output directory; existing model evidence preserved.')
    proto,d,x,structured,t,c=load(root);out.mkdir(parents=True,exist_ok=True)
    if min(np.sum(c==1),np.sum(c==2))<4:raise ValueError('Insufficient cause-specific events for this demo fit; complete interface audit instead')
    idx=np.arange(len(x));tr,te=train_test_split(idx,test_size=.25,random_state=730,stratify=c);tr=np.sort(tr);te=np.sort(te)
    pd.DataFrame({'patient_id':d.index,'role':np.where(np.isin(idx,te),'test','development'),'origin':proto['origin']}).to_csv(out/'patient_split.csv',index=False)
    metrics=[];cal=[];predictions=[];models={}
    for branch,frame in [('structured',structured),('structured_and_verified_text',x)]:
        pre=make_pipeline(SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True),StandardScaler()).fit(frame.iloc[tr]);a=pre.transform(frame.iloc[tr]);b=pre.transform(frame.iloc[te]);w=censor_weights(t[tr],c[tr],t[te],c[te]);truth=(c[te]==1).astype(int)
        for kind,cls in [('interval',IntervalHazards),('cox',CoxHazards)]:
            model=cls().fit(a,t[tr],c[tr]);p=model.risk(b);assert np.isfinite(p).all() and ((p>=0)&(p<=1)).all()
            row=dict(model=kind,branch=branch,origin=proto['origin'],**scores(truth,p,w));rng=np.random.default_rng(730);boots=[]
            for _ in range(250):
                re=rng.integers(0,len(te),len(te));boots.append(scores(truth[re],p[re],w[re]))
            for k in ['auc_730','brier_730']:
                vals=[v[k] for v in boots if v[k] is not None];row[k+'_lo'],row[k+'_hi']=map(float,np.quantile(vals,[.025,.975])) if vals else (None,None)
            metrics.append(row)
            for indices in np.array_split(np.argsort(p),5):
                if w[indices].sum()>0:cal.append(dict(model=kind,branch=branch,origin=proto['origin'],n=len(indices),mean_risk=float(p[indices].mean()),observed_ipcw=float(np.average(truth[indices],weights=w[indices]))))
            predictions.extend(dict(origin=proto['origin'],patient_id=d.index[i],time=t[i],cause=int(c[i]),model=kind,branch=branch,risk=float(pr),ipcw=float(weight)) for i,pr,weight in zip(te,p,w))
            models[branch+'_'+kind]=(pre,model)
    output=pd.DataFrame(metrics);output.to_csv(out/'模型比较.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(cal).to_csv(out/'校准.csv',index=False,encoding='utf-8-sig');pd.DataFrame(predictions).to_csv(out/'测试预测和误差.csv',index=False,encoding='utf-8-sig')
    fit_frame=x.iloc[tr].copy();primary=models['structured_and_verified_text_interval'];ref=primary[0].transform(fit_frame)
    from sklearn.neighbors import NearestNeighbors
    neighbors=NearestNeighbors(n_neighbors=4).fit(ref);radius=float(np.quantile(neighbors.kneighbors(ref)[0][:,3],.95))
    bundle=dict(origin=proto['origin'],fields=FIELDS,models=models,primary='structured_and_verified_text_interval',reference=ref,neighbors=neighbors,radius=radius,limits={k:[float(fit_frame[k].min()),float(fit_frame[k].max())] for k in FIELDS if fit_frame[k].notna().any()})
    joblib.dump(bundle,out/'models.joblib');save(out/'审计.json',dict(origin=proto['origin'],n=len(x),train=len(tr),test=len(te),split_overlap=0,recurrence=int((c==1).sum()),death=int((c==2).sum()),early_censored=int(((c==0)&(t<730)).sum()),median_followup=float(np.median(t)),missing_by_field=x.isna().sum().astype(int).to_dict(),model_sha256=sha(out/'models.joblib'),input_hashes={n:sha(root/n) for n in ['protocol.json','cohort.csv','outcomes.csv','baseline_fields.csv']}));return out
def forward(bundle,values):
    if set(values)-set(FIELDS):raise ValueError('Unknown or prohibited features')
    frame=pd.DataFrame([{f:values.get(f,np.nan) for f in FIELDS}],columns=FIELDS)
    for i in BINARY:
        value=frame.iloc[0,i]
        if pd.notna(value) and value not in (0,1):raise ValueError('Invalid binary feature')
    if (frame.dropna(axis=1)<0).any().any():raise ValueError('Negative feature')
    pre,model=bundle['models'][bundle['primary']];x=pre.transform(frame);pr=float(model.risk(x)[0])
    dist=float(bundle['neighbors'].kneighbors(x,n_neighbors=3)[0][0,-1]);return pr,dist
def search(bundle,query):
    began=time.perf_counter();lo,hi=query['interval']
    if not 0<=lo<=hi<=1 or query['mode'] not in ['existing','virtual']:raise ValueError('Invalid search contract')
    fixed=query['fixed'];axes=query['axes'];age=query['age_at_index'];permitted={'eeg_epileptiform','febrile_seizure_history','seizure_free_months','seizure_count_before_remission'}
    if not set(axes)<=permitted or set(fixed)-set(FIELDS) or any(k in fixed and fixed[k] is not None for k in axes):raise ValueError('Observed fact immutable or search field prohibited')
    if query['mode']=='existing' and any(k not in query.get('unknown_fields',[]) for k in axes):raise ValueError('Only declared unknown fields may change')
    total=int(np.prod([len(v) for v in axes.values()]));budget=int(query.get('budget',512))
    if budget<1 or total>budget:raise ValueError('Search grid exceeds declared budget')
    candidates=[];reject={};seen=set()
    for values in itertools.product(*axes.values()):
        patient={**fixed,**dict(zip(axes,values))}
        try:
            if any(v is not None and (k not in bundle['limits'] or not bundle['limits'][k][0]<=v<=bundle['limits'][k][1]) for k,v in patient.items()):raise ValueError('outside_training_range')
            if all(patient.get(k) is not None for k in FIELDS[:3]) and patient[FIELDS[2]]+patient[FIELDS[0]]+patient[FIELDS[1]]/12>age+.1:raise ValueError('inconsistent_timeline')
            key=json.dumps(patient,sort_keys=True)
            if key in seen:raise ValueError('duplicate')
            seen.add(key);pr,dist=forward(bundle,patient)
            if dist>bundle['radius']:raise ValueError('outside_joint_support')
            gap=max(lo-pr,pr-hi,0.);candidates.append(dict(values=patient,risk=pr,support_distance=dist,gap=gap,hit=(gap==0)))
        except ValueError as e:reject[str(e)]=reject.get(str(e),0)+1
    candidates.sort(key=lambda r:(r['gap'],r['support_distance']));hits=[r for r in candidates if r['hit']]
    return dict(origin=bundle['origin'],status='HIT' if hits else 'NO_FEASIBLE_HIT',considered=total,rejected=reject,hits=hits,nearest=candidates[:5],elapsed_seconds=time.perf_counter()-began,interpretation='Hypothetical research scenarios only. No medication, dosing, or treatment-effect inference.')
def main():
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['demo','audit','train','predict','search']);ap.add_argument('--input',type=Path,default=Path('synthetic_input'));ap.add_argument('--out',type=Path,default=Path('synthetic_results'));ap.add_argument('--query',type=Path);a=ap.parse_args()
    if a.action=='demo':demo_inputs(a.input);a.action='train'
    if a.action=='audit':
        p,d,x,_,t,c=load(a.input);print(json.dumps(dict(origin=p['origin'],n=len(d),recurrence=int((c==1).sum()),death=int((c==2).sum()),censored=int((c==0).sum()),followup_median=float(np.median(t)))));return
    if a.action=='train':fit(a.input,a.out);return
    if not a.query:raise ValueError('JSON query required')
    p=a.out/'models.joblib'
    if sha(p)!=json.loads((a.out/'审计.json').read_text('utf-8'))['model_sha256']:raise ValueError('Model hash mismatch')
    bundle=joblib.load(p);query=json.loads(a.query.read_text('utf-8-sig'))
    if a.action=='predict':
        pr,dist=forward(bundle,query);ans=dict(origin=bundle['origin'],risk_730=pr,support_distance=dist,in_support=dist<=bundle['radius'])
    else:ans=search(bundle,query)
    print(json.dumps(ans,ensure_ascii=False,indent=2,allow_nan=False))
if __name__=='__main__':
    from algorithm import main as execute
    execute()
