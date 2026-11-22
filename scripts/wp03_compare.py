"""Paired temporal/spatial ablation with purged expanding validation folds."""
import argparse
import json
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix, balanced_accuracy_score, roc_auc_score, average_precision_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from threadpoolctl import threadpool_limits
from scripts import ingest

TEMPORAL=["peak","event_mean","prior_mean","prior_sd"]
# Fixed by calendar before loading labels. Partial local replay uses a distinct boundary.
BOUNDARIES={"local_through_september":"2026-08-01","expanded":"2026-10-01"}
MODELS={
    "logistic":(LogisticRegression(class_weight="balanced",max_iter=1000), "C",[.1,1,10]),
    "forest":(RandomForestClassifier(n_estimators=150,class_weight="balanced",random_state=42,n_jobs=1),"max_depth",[3,6,None]),
    "boosting":(HistGradientBoostingClassifier(class_weight="balanced",random_state=42,early_stopping=False),"max_leaf_nodes",[3,7,15]),
    "svm":(SVC(class_weight="balanced"),"C",[.1,1,10]),
}


def split(frame,boundary):
    valid=frame[frame.start>=boundary]
    if valid.empty:
        raise ValueError("Empty evaluation period")
    train=frame[(frame.start<boundary)&(frame.decision<valid.evidence_start.min())]
    if train.empty or train.y.nunique()!=2:
        raise ValueError("Insufficient training classes")
    assert train.decision.max()<valid.evidence_start.min()
    return train,valid


def run(version="expanded"):
    manifest=json.loads((ingest.RESULT/"manifest.json").read_text())
    if version=="expanded" and not manifest["fully_reconciled"]:
        raise ValueError("Expanded experiment requires all source partitions reconciled")
    path=ingest.DERIVED/"events.csv"
    assert ingest.digest(path)==manifest["outputs"]["events.csv"]
    frame=pd.read_csv(path,parse_dates=["start","end","decision","evidence_start"])
    if version=="local_through_september":
        # Exclude decisions requiring any October evidence.
        frame=frame[frame.decision<=pd.Timestamp("2026-10-01")]
    if frame.duplicated(["sensor","start"]).any():
        raise ValueError("Duplicate event key")
    strict=frame[frame.label.isin(["fake","real"])].copy()
    eligible=strict.dropna(subset=["idw_pm25"]).sort_values(["start","sensor"]).copy()
    eligible["y"]=eligible.label.eq("real").astype(int)
    train,test=split(eligible,pd.Timestamp(BOUNDARIES[version]))
    folds=[]
    for chunk in np.array_split(train.start.drop_duplicates().to_numpy(),4)[1:]:
        folds.append(split(train[train.start<=chunk[-1]],chunk[0]))
    out=ingest.ROOT/"results"/"wp03"/ingest.VERSION/version
    out.mkdir(parents=True,exist_ok=True)
    cv,metrics,predictions=[],[],[]
    for arm,features in {"temporal":TEMPORAL,"temporal_spatial":TEMPORAL+["idw_pm25"]}.items():
        for model,(est,param,values) in MODELS.items():
            scores=[]
            for value in values:
                pipeline=make_pipeline(SimpleImputer(strategy="median"),StandardScaler(),clone(est).set_params(**{param:value}))
                scores_at_value=[]
                for i,(tr,va) in enumerate(folds):
                    if va.y.nunique()!=2: raise ValueError("Single-class validation fold")
                    pipeline.fit(tr[features],tr.y)
                    score=balanced_accuracy_score(va.y,pipeline.predict(va[features]))
                    scores_at_value.append(score)
                    cv.append(dict(arm=arm,model=model,parameter=param,value=str(value),fold=i+1,
                                   train_end=tr.decision.max(),validation_start=va.evidence_start.min(),balanced_accuracy=score))
                scores.append(np.mean(scores_at_value))
            best=values[int(np.argmax(scores))]
            pipeline[-1].set_params(**{param:best})
            pipeline.fit(train[features],train.y)
            pred=pipeline.predict(test[features])
            score=(pipeline.decision_function(test[features]) if hasattr(pipeline,"decision_function") else pipeline.predict_proba(test[features])[:,1])
            rep=classification_report(test.y,pred,labels=[0,1],output_dict=True,zero_division=0)
            tn,fp,fn,tp=confusion_matrix(test.y,pred,labels=[0,1]).ravel()
            row=dict(arm=arm,model=model,selected=str(best),n=len(test),tn=tn,fp=fp,fn=fn,tp=tp,
                     balanced_accuracy=balanced_accuracy_score(test.y,pred),roc_auc=roc_auc_score(test.y,score),ap=average_precision_score(test.y,score))
            for i,label in enumerate(["fake","real"]):
                for key in ["precision","recall","f1-score"]:row[label+"_"+key]=rep[str(i)][key]
            metrics.append(row)
            predictions.append(test[["sensor","start","end","label"]].assign(arm=arm,model=model,prediction=pred,score=score))
    p=pd.concat(predictions)
    p.to_csv(out/"predictions.csv",index=False)
    errors=p.assign(false_negative=p.label.eq("real")&p.prediction.eq(0),false_positive=p.label.eq("fake")&p.prediction.eq(1))
    errors.groupby(["arm","model","sensor"]).agg(events=("sensor","size"),false_negatives=("false_negative","sum"),false_positives=("false_positive","sum")).to_csv(out/"errors_by_sensor.csv")
    pd.DataFrame(metrics).to_csv(out/"metrics.csv",index=False)
    pd.DataFrame(cv).to_csv(out/"tuning.csv",index=False)
    eligible.assign(partition=np.select([eligible.index.isin(train.index),eligible.index.isin(test.index)],["train","test"],default="purged"))[["sensor","start","decision","evidence_start","partition"]].to_csv(out/"partition.csv",index=False)
    ingest.write_json(out/"design.json",dict(dataset_hash=manifest["outputs"]["events.csv"],boundary=BOUNDARIES[version],strict=len(strict),eligible=len(eligible),train=len(train),test=len(test),purged=len(eligible)-len(train)-len(test),features=TEMPORAL+["idw_pm25"],selection="mean inner balanced accuracy; ties use first grid value",scope=version))
    return pd.DataFrame(metrics)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--version",choices=BOUNDARIES,default="expanded")
    with threadpool_limits(limits=1):
        print(run(parser.parse_args().version).to_string(index=False))
