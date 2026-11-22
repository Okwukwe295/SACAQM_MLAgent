"""Evaluate one decision per completed event against retrospective proxy labels."""
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, precision_score, recall_score, f1_score, roc_auc_score, average_precision_score
from wp02_prepare import OUT

FEATURES = ["peak","event_mean","prior_mean","prior_sd"]


def predict(train,test,c=1):
    # Fit every data-dependent preprocessing step using this fold alone.
    model = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                          LogisticRegression(C=c,class_weight="balanced",max_iter=1000,random_state=42))
    model.fit(train[FEATURES],train.y)
    result = test[["sensor","start","decision","y"]].copy()
    result["probability"] = model.predict_proba(test[FEATURES])[:,1]
    result["prediction"] = (result.probability >= .5).astype(int)
    return result


def future_split(frame,boundary):
    testing = frame[frame.start>=boundary]
    training = frame[(frame.start<boundary) & (frame.decision<testing.evidence_start.min())]
    assert training.decision.max()<testing.evidence_start.min()
    return training,testing


def evaluate():
    frame = pd.read_csv(OUT/"events.csv",parse_dates=["start","decision","evidence_start"])
    frame = frame[frame.label.isin(["real","fake"])].sort_values("start").copy()
    frame["y"] = frame.label.eq("real").astype(int)
    boundary = frame.iloc[int(.75*len(frame))].start
    train,test = future_split(frame,boundary)
    folds = []
    for chunk in np.array_split(train.start.drop_duplicates().sort_values().to_numpy(),4)[1:]:
        tr,va = future_split(train[train.start<=chunk[-1]],chunk[0])
        folds.append((tr,va))
    scores = []
    for c in [.1,1,10]:
        for i,(tr,va) in enumerate(folds):
            p = predict(tr,va,c)
            scores.append(dict(C=c,fold=i+1,train=len(tr),validation=len(va),
                               train_information_end=tr.decision.max(),validation_information_start=va.evidence_start.min(),
                               f1=f1_score(p.y,p.prediction,zero_division=0)))
    cv = pd.DataFrame(scores)
    cv.to_csv(OUT/"inner_folds.csv",index=False)
    best = cv.groupby("C").f1.mean().idxmax()
    spatial = []
    for sensor,held in frame.groupby("sensor"):
        spatial.append(predict(frame[frame.sensor!=sensor],held))
    results = {"future_baseline":predict(train,test),"future_tuned":predict(train,test,best),
               "held_sensor_baseline":pd.concat(spatial)}
    rows = []
    for name,p in results.items():
        assert not p.duplicated(["sensor","start"]).any()
        p.to_csv(OUT/(name+".csv"),index=False)
        tn,fp,fn,tp = confusion_matrix(p.y,p.prediction,labels=[0,1]).ravel()
        rows.append(dict(protocol=name,n=len(p),tn=tn,fp=fp,fn=fn,tp=tp,
                         precision=precision_score(p.y,p.prediction),recall=recall_score(p.y,p.prediction),
                         f1=f1_score(p.y,p.prediction),roc_auc=roc_auc_score(p.y,p.probability),
                         average_precision=average_precision_score(p.y,p.probability)))
    metrics = pd.DataFrame(rows)
    metrics.to_csv(OUT/"metrics.csv",index=False)
    print("Boundary",boundary,"train",len(train),"purged",len(frame)-len(train)-len(test),"selected C",best)
    return metrics


if __name__ == "__main__":
    print(evaluate().to_string(index=False))
