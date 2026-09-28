# ml/ — training, datasets, models (Phase 5: AI Quality Control)

Runtime inference code lives in `backend/app/ml/` and `backend/app/cv/`. This top-level
folder holds the **offline training scripts**, per the architecture in Phase 1: training does
not run automatically when the application starts (see `backend/app/main.py`'s health check,
which honestly reports `"ml": "not_configured"` until a model file exists).

## Train

```bash
cd <repo root>
source .venv/bin/activate
python ml/training/train_defect_model.py
python ml/training/train_process_model.py
```

Both scripts print the real dataset size, split sizes, training time, and evaluation metrics
(accuracy, precision/recall/F1 per class, confusion matrix where applicable), save a `.joblib`
artifact under `ml/models/` (git-ignored — regenerate locally), and write an `MLModelMetrics`
row to the database so the Quality Control dashboard shows the same numbers this script
printed, not hardcoded ones.

## Honesty disclaimer (required, shown everywhere these metrics appear)

> Metrics are based on the supplied demonstration/synthetic dataset and do not represent
> industrial validation.

No real print-defect photographs or production process telemetry were supplied with this
project. `train_defect_model.py --data-dir <folder>` accepts real labelled photos instead
(layout: `<folder>/<CLASS_NAME>/*.png`); without `--data-dir` it trains on procedurally
generated synthetic images with strong, clean visual signatures per class, which explains why
accuracy on this specific dataset is very high — that is a property of the synthetic data, not
a claim about performance on real photographs.

## Production migration

`DefectDetector.predict()` in `backend/app/ml/quality_model.py` is the substitution seam: a
YOLO/TensorFlow CNN inference service can replace the classical-CV-features + Random-Forest
pipeline without changing `services/quality.py` or the API.
