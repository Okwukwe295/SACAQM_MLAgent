A chronological time-based train-test split was used instead of a random split. This was done because the intended use of the model is to classify future spike candidates using patterns learned from earlier labelled events. In a real deployment setting, future spike events would not be available during model training, so the evaluation should reflect this by training the model on earlier events and testing it on later unseen events.

This approach also reduces the risk of temporal leakage, where similar events from the same time period could appear in both the training and testing sets. If random splitting was used, the model could be tested on events that are very similar to events it had already seen during training, giving an overly optimistic estimate of performance. A time-based split provides a stricter and more realistic test of whether the model can generalise to new spike events over time.

Although the goal is to learn the difference between real pollution spikes and fake sensor artifacts based on event features, sensor behaviour, environmental conditions, missing data patterns, and pollution activity may change over time. Therefore, evaluating the model on later spike events helps assess whether the learned feature patterns remain useful under future conditions.


## Model Evaluation Metrics

After training the logistic regression model, the model was evaluated on the future test set. The test set contains spike events that happened after the training period, so this evaluation helps check how well the model may perform on future unseen spikes.

### Confusion Matrix

The confusion matrix shows the number of correct and incorrect predictions made by the model.

For this project:

* **True fake**: a suspected fake sensor artefact correctly predicted as fake.
* **Fake predicted as real**: a suspected fake sensor artefact incorrectly accepted as a real pollution spike.
* **Real predicted as fake**: a genuine pollution spike incorrectly rejected as fake.
* **True real**: a genuine pollution spike correctly predicted as real.

This is useful because it shows the actual types of mistakes the model is making. In this project, fake spikes predicted as real are problematic because sensor artefacts may be treated as real air pollution events. Real spikes predicted as fake are also problematic because genuine pollution events may be missed.

### Accuracy

Accuracy measures the overall percentage of correct predictions.

It answers:

“How many spike events did the model classify correctly overall?”

For this project, accuracy gives a general idea of performance, but it should not be used alone because the dataset may be imbalanced. For example, if there are more fake spikes than real spikes, the model could get a high accuracy by mostly predicting the majority class.

### Precision

Precision measures how correct the model is when it predicts a certain class.

For the **real** class, precision answers:

“When the model predicts that a spike is real, how often is it actually real?”

High real precision means the model is not falsely accepting many fake sensor artefacts as real pollution spikes.

For this project, high real precision is important if we want to avoid false pollution alerts caused by faulty sensors or sensor artefacts.

### Recall

Recall measures how many actual examples of a class the model successfully finds.

For the **real** class, recall answers:

“Out of all truly real pollution spikes, how many did the model correctly detect?”

High real recall means the model is good at finding genuine pollution events.

For this project, high real recall is important because we do not want the system to miss real air pollution spikes.

### F1-score

The F1-score combines precision and recall into one balanced metric.

It is useful when we want to balance two goals:

* avoiding fake spikes being classified as real
* avoiding real spikes being missed

For this project, the F1-score is useful because both types of errors matter. A high F1-score means the model has a good balance between correctly detecting real spikes and avoiding false real-spike predictions.

### Support

Support is the number of true examples of each class in the test set.

For example, support tells us how many real spikes and how many fake spikes were actually present in the future test set.

This is important because it helps us judge whether the evaluation is reliable. If one class has very few examples, the precision, recall, and F1-score for that class may not be very stable.

### ROC-AUC

ROC-AUC measures how well the model separates real spikes from fake spikes using probability scores.

It does not only look at the final prediction. Instead, it checks whether real spikes generally receive higher “probability of being real” scores than fake spikes.

For this project, a high ROC-AUC means the model is good at ranking genuine pollution spikes above suspected sensor artefacts.

General interpretation:

* 0.5 means the model is close to random guessing.
* 0.7 means the model has some useful separation ability.
* 0.8 or above suggests good separation.
* 0.9 or above suggests very strong separation.

### Average Precision

Average precision evaluates how well the model identifies the positive class across different probability thresholds.

In this project, the positive class is:

real spike = 1

Average precision is useful because the dataset is not perfectly balanced. It focuses on how well the model identifies real pollution spikes while considering the confidence scores.

For this project, a high average precision means the model is good at assigning high real-spike probabilities to actual real pollution events.

### Macro Average

The macro average calculates the metric separately for each class and then takes the simple average.

This treats fake and real spikes equally, regardless of how many examples each class has.

For this project, macro average is useful because we care about performance on both real and fake spike classes, even if one class has fewer examples.

### Weighted Average

The weighted average also calculates the metric for each class, but it gives more weight to the class with more examples.

This reflects overall performance across the dataset, but it may hide poor performance on the smaller class.

For this project, weighted average is useful, but it should be interpreted alongside the class-specific precision, recall, and F1-scores.

### Overall Meaning for the Project

These metrics help determine whether the logistic regression model can reliably classify future spike events as either real pollution spikes or fake sensor artefacts. The most important results to inspect are the confusion matrix, real-class precision, real-class recall, F1-score, ROC-AUC, and average precision.

For this project, the model should ideally have:

* high real precision, so fake artefacts are not incorrectly accepted as real pollution events
* high real recall, so genuine pollution spikes are not missed
* a strong F1-score, showing a good balance between precision and recall
* a high ROC-AUC, showing that real spikes are generally ranked above fake spikes
* a high average precision, showing that the model is effective at identifying real spikes using probability scores


GridSearchCV is a method provided by the scikit-learn library in Python, which is used to systematically work through multiple combinations of parameter tunes, cross-validating as it goes to determine which tune gives the best performance.

https://www.geeksforgeeks.org/machine-learning/how-to-optimize-logistic-regression-performance/

|Penalty| What it does |Compatible solver examples|
| `l2`  | Shrinks coefficients smoothly | `lbfgs`, `newton-cg`, `sag`, `saga`, `liblinear`|
| `l1`| Can shrink some coefficients to exactly zero | `liblinear`, `saga`|
| `elasticnet` | Mixes L1 and L2 | `saga` only |
| `None` | No regularisation | not `liblinear`|


### RULE-DERIVED ASSUMPTIONS

1. Confirmed Real — confirmed_real_close_duration

A spike candidate is labelled real when:
At least one neighbouring sensor also experiences a spike at approximately the same time, and the neighbouring spike has a similar duration to the target sensor's spike.

Formally:
n_close_duration_neighbours >= 1


For a neighbour to count as a close-duration neighbour:
target_duration_timesteps >= 1 AND neighbour_duration_timesteps >= 1 AND abs(target_duration_timesteps - neighbour_duration_timesteps) <= 1


Therefore, the duration tolerance is ±1 timestep/hour.

Assumption
A genuine pollution event is expected to have some spatial consistency. If a nearby sensor independently detects a spike at approximately the same time and for approximately the same duration, this provides evidence that the increase represents a real environmental event rather than an isolated sensor malfunction.

2. Suspected Fake — suspected_fake_sensor_artifact

A spike candidate is labelled fake/sensor artifact only when all of the following conditions are satisfied:
n_neighbours_checked > 0 AND n_active_neighbour_spikes == 0 AND target_duration_timesteps == 1 AND sharp_jump == True AND sharp_drop_after_event == True AND returns_to_normal_quickly == True


So there are several pieces of evidence being combined.
Spatial evidence: at least one neighbouring sensor was available to check, but none of those neighbours showed a corresponding spike.
Duration evidence: the spike lasted only one timestep.
Shape evidence: the reading showed a sharp increase, followed by a sharp decrease after the event, and then quickly returned to its normal/baseline behaviour.

Assumption
An isolated, short-lived, abrupt excursion that immediately disappears and is not observed by nearby sensors is more consistent with a sensor-specific artifact than a genuine environmental pollution event.

3. Spatially Supported but Different Duration — spatially_supported_different_duration
This occurs when neighbouring sensors provide spatial evidence of an event, but their event durations do not satisfy your ±1 timestep duration-matching requirement.
Conceptually:
Neighbouring spike exists
        +
No neighbour has sufficiently close duration
        ↓
spatially_supported_different_duration

Assumption
There is evidence that something real may have happened in the area, but the temporal behaviour across sensors isn't similar enough to satisfy your stronger definition of a confirmed real spike.
Therefore, you don't force this candidate into either the real or fake training class.

4. Isolated / Unconfirmed
These are candidates for which there isn't enough evidence to confidently call them either real or fake.
This includes cases such as:
Target sensor detects spike
        ↓
No sufficient supporting evidence
        ↓
But candidate DOES NOT satisfy
all fake-artifact conditions
        ↓
UNCONFIRMED

It can also include situations where neighbouring sensors aren't sufficiently available to make a meaningful spatial comparison.
Assumption
Absence of evidence is not automatically evidence that the spike is fake.
This is an important part of your methodology. A spike isn't labelled fake simply because another sensor didn't detect it. It needs the additional one-timestep + sharp-jump + sharp-drop + quick-return behaviour.
Overall decision structure
Your labelling logic can therefore be summarized as:

                     SPIKE CANDIDATE
                           │
                           ▼
                 Check neighbouring sensors
                           │
              ┌────────────┴─────────────┐
              │                          │
       Neighbour spike             No neighbour spike
              │                          │
              ▼                          ▼
     Compare event duration       Check artifact pattern
              │                          │
       ┌──────┴──────┐             ┌────┴──────────┐
       │             │             │               │
   Within ±1      Different      All fake        Conditions
    timestep       duration      conditions       not met
       │             │             │               │
       ▼             ▼             ▼               ▼
 CONFIRMED       SPATIALLY      SUSPECTED       UNCONFIRMED
    REAL         SUPPORTED         FAKE
                 DIFFERENT       ARTIFACT
                 DURATION