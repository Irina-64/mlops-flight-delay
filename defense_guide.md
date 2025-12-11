# Защита проекта: Система предсказания задержек рейсов (Flight Delay Prediction)

## Пошаговое описание и сценарий защиты

---

## 📋 ВВЕДЕНИЕ И КОНТЕКСТ (2-3 минуты)

### Слайд 1: Название и цель проекта

```
Система предсказания задержек рейсов: Full MLOps Pipeline
Flight Delay Prediction System with Complete CI/CD, Monitoring & Feature Store

Цель проекта:
✅ Разработать production-ready ML систему для прогноза задержек авиарейсов
✅ Реализовать full MLOps pipeline с CI/CD и мониторингом
✅ Демонстрировать best practices: DVC, Feature Store, Kubernetes, GitOps
```

### Что вы покажете:
1. **Полный MLOps цикл** — от данных до production
2. **CI/CD pipeline** — автоматизированное развертывание
3. **Feature Store** — управление признаками (Feast)
4. **Мониторинг** — отслеживание качества моделей
5. **API и инференс** — REST сервис для предсказаний

---

## 🏗️ АРХИТЕКТУРА СИСТЕМЫ (3-4 минуты)

### Слайд 2: Общая архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                    DATA SOURCES                             │
│         (Historical flights, Weather, Airlines)             │
└────────────────────┬────────────────────────────────────────┘
                     │
        ┌────────────▼──────────────┐
        │   DATA PIPELINE (DVC)     │
        │  ├─ preprocess.py         │
        │  ├─ feature_eng.py        │
        │  └─ validate.py           │
        └────────────┬───────────────┘
                     │
        ┌────────────▼──────────────────┐
        │     FEATURE STORE (Feast)    │
        │  ├─ Offline (BigQuery/S3)    │
        │  └─ Online (Redis)           │
        └────────────┬──────────────────┘
                     │
        ┌────────────▼──────────────┐
        │  MODEL TRAINING           │
        │  ├─ Gradient Boosting      │
        │  ├─ Neural Network         │
        │  └─ Model Registry (MLflow)│
        └────────────┬───────────────┘
                     │
        ┌────────────▼──────────────┐
        │  CI/CD PIPELINE            │
        │  ├─ .github/workflows/ci.yml
        │  └─ .github/workflows/deploy.yml
        └────────────┬───────────────┘
                     │
        ┌────────────▼──────────────┐
        │  KUBERNETES DEPLOYMENT    │
        │  ├─ API Service (FastAPI) │
        │  ├─ Monitoring (Prometheus)
        │  └─ Feature Service       │
        └─────────────────────────────┘
                     │
        ┌────────────▼──────────────┐
        │  MONITORING & OBSERVABILITY
        │  ├─ Model metrics         │
        │  ├─ Data quality checks   │
        │  ├─ Alerts                │
        │  └─ Dashboards (Grafana)  │
        └───────────────────────────┘
```

### Что показать:
- **Data layer**: источники данных (flight history, weather, airlines)
- **Processing**: DVC pipeline для воспроизводимости
- **Feature Store**: Feast для управления признаками
- **Models**: несколько моделей в Model Registry
- **Deployment**: Docker + Kubernetes
- **Monitoring**: метрики и алерты

---

## 📊 ДАННЫЕ И ИССЛЕДОВАТЕЛЬСКИЙ АНАЛИЗ (3-4 минуты)

### Слайд 3: Датасет

```
Datasets used:
├─ Flight history (1M+ flights)
│  ├─ flight_id, airline, departure_time, arrival_time
│  ├─ actual_delay_minutes (target)
│  └─ route, aircraft_type, time_of_day
│
├─ Weather data (hourly)
│  ├─ temperature, humidity, wind_speed
│  ├─ visibility, precipitation
│  └─ conditions (clear, rain, snow, fog)
│
└─ Airline performance (aggregated)
   ├─ airline_on_time_percentage
   ├─ historical_average_delay
   └─ reliability_score

Time period: 2022-2024 (3 years)
Train/Val/Test split: 60% / 20% / 20%
Temporal split: chronological (no future leakage)
```

### Показать в коде:
```bash
# Проверить DVC pipeline для данных
dvc dag --ascii

# Показать размеры датасетов
ls -lh data/raw/
ls -lh data/processed/

# Статистика
python src/eda.py --show-stats
```

---

## 🔧 FEATURE ENGINEERING (3 минуты)

### Слайд 4: Признаки и Feature Store

```
OFFLINE FEATURES (для обучения):
├─ Route aggregates
│  ├─ avg_delay_7d (средняя задержка за 7 дней)
│  ├─ std_delay_7d (стандартное отклонение)
│  └─ on_time_percentage_7d
│
├─ Airline features
│  ├─ airline_avg_delay_30d
│  ├─ airline_reliability_score
│  └─ airline_cancellation_rate
│
├─ Time-based features
│  ├─ hour_of_day, day_of_week
│  ├─ is_holiday, is_peak_hour
│  └─ season
│
└─ Weather features
   ├─ avg_temperature, humidity
   ├─ wind_speed, visibility
   └─ weather_condition (encoded)

ONLINE FEATURES (для инференса):
├─ Real-time aggregates (обновляются streaming)
├─ Current weather (от API)
├─ Live airline status
└─ Cached aggregates (Redis)

Feature groups in Feast:
├─ route_features (source: BigQuery, frequency: daily batch)
├─ airline_features (source: S3, frequency: daily batch)
├─ weather_features (source: Kafka, frequency: streaming)
└─ temporal_features (computed, frequency: on-demand)
```

### Показать в коде:
```bash
# Feast features registry
feast feature-store.yaml

# Validate features
pytest tests/test_features.py -v

# Feature statistics
python src/feature_stats.py
```

---

## 🤖 МОДЕЛИ (4-5 минут)

### Слайд 5: Архитектура моделей

```
MODEL 1: Gradient Boosting (XGBoost)
├─ Type: Tree-based, interpretable
├─ Hyperparameters: max_depth=6, n_estimators=200, learning_rate=0.05
├─ Training time: ~5 minutes
├─ Baseline performance:
│  ├─ MAE: 12.3 minutes
│  ├─ RMSE: 28.5 minutes
│  ├─ R²: 0.78
│  └─ Feature importance: top 10 analyzed
└─ Size: 45 MB

MODEL 2: Neural Network (PyTorch/TensorFlow)
├─ Type: Deep Learning, end-to-end learning
├─ Architecture:
│  ├─ Input layer: 45 features
│  ├─ Hidden layers: [256, 128, 64] with BatchNorm + Dropout
│  ├─ Output layer: 1 (regression)
│  └─ Activation: ReLU + Sigmoid
├─ Hyperparameters: epochs=50, batch_size=32, lr=0.001
├─ Training time: ~20 minutes
├─ Performance:
│  ├─ MAE: 11.8 minutes
│  ├─ RMSE: 27.2 minutes
│  ├─ R²: 0.80
│  └─ Better on complex patterns
└─ Size: 12 MB

MODEL SELECTION:
├─ Ensemble: Weighted average (XGBoost 60%, NN 40%)
├─ Final performance:
│  ├─ MAE: 11.5 minutes
│  ├─ RMSE: 26.8 minutes
│  └─ R²: 0.81
└─ Deployed in production
```

### Показать в коде:
```bash
# Обучение моделей (воспроизводимо через DVC)
dvc repro training_stage

# Сравнение моделей
python src/compare_models.py

# MLflow UI с метриками
mlflow ui  # http://localhost:5000

# Выберите best model в registry
# Stage: Production
```

### Демонстрация кода:
```python
# src/train.py snippet
import xgboost as xgb
from sklearn.metrics import mean_absolute_error

# Reproducible training with DVC
X_train, y_train = load_features("train")
model = xgb.XGBRegressor(
    max_depth=6,
    n_estimators=200,
    learning_rate=0.05,
    random_state=42
)
model.fit(X_train, y_train)

# Log to MLflow
mlflow.log_param("max_depth", 6)
mlflow.log_metric("train_mae", mean_absolute_error(...))
mlflow.sklearn.log_model(model, "xgboost_model")
```

---

## 🚀 CI/CD PIPELINE (3-4 минуты)

### Слайд 6: GitHub Actions Workflow

```
PUSH TO BRANCH → CI PIPELINE
├─ Stage 1: LINT & FORMAT
│  ├─ flake8, black, isort, mypy
│  └─ Quality gates (5 minutes)
│
├─ Stage 2: UNIT TESTS
│  ├─ pytest tests/ (--cov=src)
│  ├─ Coverage: >85%
│  └─ Time: 10 minutes
│
├─ Stage 3: DATA VALIDATION
│  ├─ Great Expectations checks
│  ├─ DVC pull (fetch data)
│  └─ Data quality gates
│
├─ Stage 4: DVC PIPELINE
│  ├─ dvc repro (preprocessing, training)
│  ├─ Artifact tracking
│  └─ Time: 30 minutes
│
├─ Stage 5: SECURITY SCAN
│  ├─ bandit (security issues)
│  ├─ safety (vulnerable dependencies)
│  └─ SBOM generation
│
└─ Stage 6: BUILD DOCKER IMAGE
   ├─ Multi-stage Dockerfile
   ├─ Push to GHCR
   └─ Image size: 450 MB

MERGE TO MAIN → CD PIPELINE
├─ Stage 1: VALIDATE K8S MANIFESTS
│  ├─ kubectl apply --dry-run
│  └─ Helm lint (if using Helm)
│
├─ Stage 2: DEPLOY TO STAGING
│  ├─ kubectl apply -f k8s/
│  ├─ Smoke tests
│  └─ Health checks
│
├─ Stage 3: RUN INTEGRATION TESTS
│  ├─ API endpoint tests
│  ├─ End-to-end inference
│  └─ Latency checks
│
├─ Stage 4: DEPLOY TO PRODUCTION
│  ├─ Canary rollout (10% → 100%)
│  ├─ Blue-green deployment
│  └─ Monitoring alerts
│
└─ Stage 5: NOTIFY
   ├─ Slack notification
   ├─ GitHub Release
   └─ Team dashboard updated

Total CI time: ~50 minutes
Total CD time: ~20 minutes
```

### Показать в коде:
```bash
# Просмотр workflow статуса
gh run list

# Посмотреть last build logs
gh run view <run-id> --log

# Trigger manually (если надо)
gh workflow run ci.yml --ref main
```

### Открыть в GitHub:
```
GitHub → Actions → CI - Test & Build / Deploy to Kubernetes
Показать: ✅ All stages passed
Commit: "feat: add prediction batch endpoint"
Time: 48 minutes
```

---

## 🐳 DEPLOYMENT & KUBERNETES (3-4 минуты)

### Слайд 7: Deployment архитектура

```
DOCKER IMAGE
├─ Base: python:3.11-slim
├─ Multi-stage build
│  ├─ Builder stage: install dependencies
│  └─ Runtime stage: minimal image
├─ Non-root user (security)
├─ Health checks
└─ Size: 450 MB

KUBERNETES MANIFESTS (k8s/)
├─ deployment.yaml
│  ├─ Replicas: 3 (high availability)
│  ├─ Resource requests: CPU 500m, Memory 512Mi
│  ├─ Resource limits: CPU 1000m, Memory 1Gi
│  ├─ Liveness probe: /health (30s)
│  ├─ Readiness probe: /ready (10s)
│  └─ Rolling update strategy
│
├─ service.yaml
│  ├─ Type: LoadBalancer (or NodePort for dev)
│  ├─ Port: 80 → 9696
│  └─ Session affinity: ClientIP
│
├─ hpa.yaml (Horizontal Pod Autoscaler)
│  ├─ Min replicas: 2
│  ├─ Max replicas: 10
│  ├─ Target CPU: 70%
│  ├─ Target Memory: 80%
│  └─ Scale-up: fast, Scale-down: slow
│
├─ configmap.yaml
│  ├─ MODEL_PATH: /models/flight_delay_model.pkl
│  ├─ DATA_PATH: /data
│  └─ LOG_LEVEL: INFO
│
└─ resources/
   ├─ network-policy.yaml (restrict traffic)
   ├─ pod-disruption-budget.yaml (availability)
   └─ service-monitor.yaml (Prometheus scrape)

DEPLOYMENT FLOW:
1. Image pushed to GHCR
2. K8s pulls latest image
3. New pods start with liveness/readiness checks
4. Old pods drain gracefully (pre-stop hook)
5. Service routes traffic to healthy pods
6. HPA monitors and scales as needed
```

### Показать в коде:
```bash
# Развернуть локально (Minikube)
minikube start
make deploy-minikube

# Проверить pods
kubectl get pods -o wide
kubectl describe pod <pod-name>

# Посмотреть логи
kubectl logs -f deployment/flight-delay-api

# Port forward
kubectl port-forward svc/flight-delay-api 9696:80

# Посмотреть HPA
kubectl get hpa -w
```

### Создать load и показать scaling:
```bash
# Terminal 1: watch HPA
kubectl get hpa -w

# Terminal 2: create load
while true; do curl -X POST http://localhost:9696/predict \
  -H "Content-Type: application/json" \
  -d '{"route":"JFK-LAX", "airline":"AA"}'; done

# Наблюдать: replicas: 3 → 5 → 8 (по CPU)
```

---

## 📡 FEATURE STORE (FEAST) (2-3 минуты)

### Слайд 8: Feature Store Integration

```
FEAST REGISTRY
├─ feature_store.yaml
│  ├─ Project: flight-delay
│  ├─ Provider: local (or GCP/AWS)
│  └─ Online store: redis
│
├─ features/
│  ├─ route_features.py
│  │  ├─ avg_delay_7d
│  │  ├─ on_time_percentage
│  │  └─ volume_7d
│  │
│  ├─ airline_features.py
│  │  ├─ airline_avg_delay_30d
│  │  ├─ cancellation_rate
│  │  └─ reliability_score
│  │
│  └─ temporal_features.py
│     ├─ hour_of_day, day_of_week
│     └─ is_peak_hour, is_holiday
│
└─ WORKFLOW:
   ├─ Offline: Training data with point-in-time correctness
   ├─ Online: Real-time feature serving (Redis)
   └─ Sync: Batch → Redis every hour

FEAST COMMANDS:
├─ feast feature-store.yaml (validate registry)
├─ feast apply (register features)
├─ feast materialize (batch → online)
└─ feast get-online-features (runtime lookup)
```

### Показать в коде:
```bash
# Validate feature registry
feast feature-store.yaml

# List all features
feast feature-view list

# Materialize features to online store
feast materialize 2024-01-01 2024-01-31

# Get historical features (for training)
python -c "
from feast import FeatureStore
fs = FeatureStore(repo_path='.')
training_data = fs.get_historical_features(
    entity_df=...,
    features=['route_features:avg_delay_7d', ...],
    full_feature_names=True
)
print(training_data)
"
```

---

## 📈 МОНИТОРИНГ И OBSERVABILITY (3-4 минуты)

### Слайд 9: Monitoring Stack

```
METRICS COLLECTED
├─ Model Metrics (Prometheus)
│  ├─ Predictions per second (RPS)
│  ├─ Prediction latency (p50, p95, p99)
│  ├─ Model inference errors
│  └─ Model version in use
│
├─ Data Quality Metrics
│  ├─ Feature staleness (hours)
│  ├─ Null rate per feature (%)
│  ├─ Value distribution (histogram)
│  ├─ Data drift (PSI, KS-statistic)
│  └─ Pipeline success rate
│
├─ Infrastructure Metrics
│  ├─ CPU / Memory usage per pod
│  ├─ Pod restart count
│  ├─ Network I/O
│  └─ Disk usage
│
└─ Business Metrics
   ├─ Prediction accuracy by airline
   ├─ Prediction accuracy by route
   ├─ Mean Absolute Error (MAE)
   ├─ Service availability (%)
   └─ Cost per prediction ($)

DASHBOARDS (Grafana)
├─ Dashboard 1: Overview
│  ├─ RPS, latency, errors
│  ├─ Pod status, HPA scaling
│  └─ Recent alerts
│
├─ Dashboard 2: Model Health
│  ├─ Accuracy metrics
│  ├─ Data drift detection
│  ├─ Feature staleness
│  └─ Training history (from MLflow)
│
└─ Dashboard 3: Business KPIs
   ├─ Accuracy by airline
   ├─ Accuracy by route
   ├─ Cost per prediction
   └─ SLA compliance (%)

ALERTING (AlertManager)
├─ 🔴 Critical:
│  ├─ Error rate > 5%
│  ├─ Pod CrashLoopBackOff
│  ├─ Data drift detected (PSI > 0.25)
│  └─ Model accuracy < 0.75
│
├─ 🟡 Warning:
│  ├─ Latency p99 > 500ms
│  ├─ Feature staleness > 2 hours
│  ├─ CPU > 80% for 5 min
│  └─ Null rate > 1%
│
└─ 🔵 Info:
   ├─ Deployment started
   ├─ Deployment completed
   └─ Model updated

ALERTING CHANNELS
├─ PagerDuty (critical, on-call engineer)
├─ Slack (warnings and updates)
└─ Email (weekly summary)
```

### Показать в демо:
```bash
# Prometheus metrics endpoint
curl http://localhost:9696/metrics

# Grafana dashboard
open http://localhost:3000
# Login: admin / admin
# Show: Dashboard → Flight Delay Monitoring

# Trigger synthetic load
python tests/load_test.py --duration 2m --rps 100

# Watch metrics in real-time
watch 'curl -s http://localhost:9696/metrics | grep flight_'
```

---

## 🔍 TESTING (2-3 минуты)

### Слайд 10: Testing Strategy

```
UNIT TESTS (tests/test_*.py)
├─ test_preprocess.py
│  ├─ Test feature transformations
│  ├─ Test edge cases (missing values, outliers)
│  └─ Test data validation
│
├─ test_api.py
│  ├─ Test /health endpoint
│  ├─ Test /predict endpoint
│  ├─ Test input validation
│  └─ Test error handling
│
├─ test_model.py
│  ├─ Test model loading
│  ├─ Test model inference
│  ├─ Test batch prediction
│  └─ Test model output shape/type
│
└─ test_features.py
   ├─ Test feature computation
   ├─ Test feature schema
   ├─ Test null rate < threshold
   └─ Test value ranges

INTEGRATION TESTS (tests/integration/)
├─ test_e2e.py
│  ├─ Load features from Feature Store
│  ├─ Run full inference pipeline
│  ├─ Compare with baseline
│  └─ Check latency SLA
│
└─ test_drift_detection.py
   ├─ Test data drift detection
   ├─ Test staleness monitoring
   └─ Alert triggering

COVERAGE
├─ Current: 87% (target: >85%)
├─ Critical paths: 100%
└─ Excluded: __init__, config, logging

TEST EXECUTION
├─ pytest tests/ --cov=src --cov-report=html
├─ Coverage report: htmlcov/index.html
└─ CI: runs on every commit
```

### Показать в коде:
```bash
# Run all tests
pytest tests/ -v --cov=src

# Run specific test
pytest tests/test_api.py::test_predict_endpoint

# Generate coverage report
pytest tests/ --cov=src --cov-report=html
open htmlcov/index.html

# Show current coverage
coverage report
```

---

## 🎯 REST API (2 минуты)

### Слайд 11: API Endpoints

```
API SPECIFICATION (FastAPI)
├─ Base URL: http://api.flight-delay.com
├─ Timeout: 30 seconds
└─ Rate limit: 1000 req/min per API key

ENDPOINTS:
1. GET /health
   └─ Status: 200 OK
   └─ Response: {"status": "healthy", "version": "v1.2.3"}

2. GET /ready
   └─ Status: 200 OK
   └─ Response: {"ready": true, "model_loaded": true}

3. POST /predict
   ├─ Input: {
   │    "route": "JFK-LAX",
   │    "airline": "AA",
   │    "departure_time": "2024-01-15T14:30:00",
   │    "aircraft_type": "Boeing 737",
   │    "weather_condition": "clear"
   │  }
   │
   ├─ Output: {
   │    "delay_minutes": 18.5,
   │    "confidence": 0.92,
   │    "model_version": "v2.1.0",
   │    "features_used": ["avg_delay_7d", "airline_score", ...],
   │    "inference_time_ms": 45
   │  }
   │
   └─ Status: 200 OK

4. POST /predict-batch
   ├─ Input: [{route, airline, ...}, ...]
   ├─ Output: [{delay_minutes, confidence}, ...]
   └─ Optimized for bulk predictions

5. GET /metrics
   └─ Prometheus metrics (for monitoring)

6. GET /model-info
   └─ Current model version, training date, etc.

ERROR HANDLING:
├─ 400: Bad request (invalid input)
├─ 503: Service unavailable (model not loaded)
├─ 504: Gateway timeout (slow prediction)
└─ 500: Internal server error (unexpected issue)
```

### Показать в демо:
```bash
# Start API locally
python -m src.api

# Test health
curl http://localhost:9696/health

# Test prediction
curl -X POST http://localhost:9696/predict \
  -H "Content-Type: application/json" \
  -d '{
    "route": "JFK-LAX",
    "airline": "AA",
    "departure_time": "2024-01-15T14:30:00",
    "aircraft_type": "Boeing 737",
    "weather_condition": "clear"
  }'

# Response:
# {
#   "delay_minutes": 18.5,
#   "confidence": 0.92,
#   "model_version": "v2.1.0",
#   "inference_time_ms": 45
# }

# Batch prediction
curl -X POST http://localhost:9696/predict-batch \
  -H "Content-Type: application/json" \
  -d '[
    {"route": "JFK-LAX", "airline": "AA", ...},
    {"route": "SFO-ORD", "airline": "UA", ...}
  ]'
```

---

## 📊 РЕЗУЛЬТАТЫ И МЕТРИКИ (3-4 минуты)

### Слайд 12: Project Results

```
MODEL PERFORMANCE
├─ Baseline (Simple Mean): MAE = 45 minutes, R² = 0.20
├─ XGBoost Model: MAE = 12.3 min, R² = 0.78, Training time: 5 min
├─ Neural Network: MAE = 11.8 min, R² = 0.80, Training time: 20 min
└─ Ensemble: MAE = 11.5 min, R² = 0.81 ⭐ BEST

ACCURACY BY AIRLINE:
├─ American Airlines (AA): MAE = 10.2 min
├─ United Airlines (UA): MAE = 11.8 min
├─ Delta Airlines (DL): MAE = 12.1 min
└─ Southwest Airlines (SW): MAE = 13.4 min

ACCURACY BY ROUTE:
├─ JFK-LAX: MAE = 9.5 min (high traffic, predictable)
├─ SFO-ORD: MAE = 11.2 min
├─ LAX-DEN: MAE = 8.7 min (mountain airport, very predictable)
└─ ATL-SEA: MAE = 15.3 min (weather volatile)

SYSTEM METRICS
├─ API Latency:
│  ├─ p50: 45 ms
│  ├─ p95: 120 ms
│  └─ p99: 250 ms (SLA: < 500 ms ✅)
│
├─ Throughput:
│  ├─ Current: 500 RPS
│  ├─ Peak capacity: 2000 RPS (with HPA)
│  └─ Cost per prediction: $0.002
│
├─ Availability:
│  ├─ Uptime: 99.98%
│  ├─ Mean time to recovery (MTTR): 8 minutes
│  └─ SLA: 99.95% ✅
│
└─ Data Quality:
   ├─ Feature staleness: < 1 hour
   ├─ Null rate: 0.02% (< 1% ✅)
   ├─ Data drift detected: 0 (monitored ✅)
   └─ Pipeline success rate: 99.9%

PRODUCTION IMPACT
├─ Business:
│  ├─ Reduces customer rebooking delays by 25%
│  ├─ Improves operational planning accuracy
│  └─ Estimated annual savings: $500K
│
└─ Technical:
   ├─ End-to-end latency: < 1 second
   ├─ Model retraining: automated (weekly)
   ├─ Feature store: 100+ features, 0 conflicts
   └─ CI/CD cycle time: < 1 hour
```

### Показать на графиках:
```
📈 Accuracy over time (retrain週ごと):
   MAE trend: 45 → 25 → 15 → 11.5 (improving with retraining)

📊 Latency distribution (histogram):
   p50, p95, p99 (show tail latency under load)

🎯 Accuracy by airline (bar chart):
   AA > UA > DL > SW (differences explained by features)

📉 Data drift detection (time series):
   PSI score trending: 0.05 (stable, no alerts)
```

---

## 🔄 DEPLOYMENT STRATEGY (2 минуты)

### Слайд 13: CI/CD Deployment Pipeline

```
DEPLOYMENT STAGES:
├─ Stage 1: COMMIT TO FEATURE BRANCH
│  └─ Trigger: CI tests + security scan
│
├─ Stage 2: PULL REQUEST
│  ├─ Require: ✅ All tests pass
│  ├─ Require: ✅ Code review approved
│  └─ Require: ✅ No conflicts
│
├─ Stage 3: MERGE TO MAIN
│  └─ Trigger: CD pipeline starts
│
├─ Stage 4: BUILD & PUSH IMAGE
│  ├─ Docker build (multi-stage)
│  ├─ Security scan (Trivy)
│  └─ Push to GHCR
│
├─ Stage 5: DEPLOY TO STAGING
│  ├─ kubectl apply -f k8s/ (staging)
│  ├─ Health checks: 200s for all pods
│  └─ Run smoke tests
│
├─ Stage 6: VALIDATION (STAGING)
│  ├─ API endpoint tests
│  ├─ Feature freshness checks
│  ├─ Prediction accuracy validation
│  └─ Load test (1000 RPS, 2 min)
│
├─ Stage 7: PROMOTE TO PRODUCTION
│  ├─ Canary rollout: 10% traffic for 10 min
│  ├─ Monitor: error rate, latency, accuracy
│  ├─ If OK: 50% for 10 min
│  ├─ If OK: 100% (full rollout)
│  └─ If error: automatic rollback
│
└─ Stage 8: POST-DEPLOYMENT
   ├─ Run regression tests
   ├─ Verify all monitoring alerts active
   ├─ Update documentation
   └─ Notify team (Slack)

ROLLBACK STRATEGY:
├─ Automatic rollback if:
│  ├─ Error rate > 5%
│  ├─ Model accuracy < 0.75
│  └─ Latency p99 > 2000ms
│
├─ Manual rollback: gh deployment list / gh deployment destroy
└─ Recovery time: < 5 minutes
```

---

## 💡 KEY ACHIEVEMENTS & LEARNINGS (2 минуты)

### Слайд 14: What We Accomplished

```
✅ COMPLETED:
├─ Full MLOps pipeline from data to production
├─ DVC for reproducible training
├─ Feature Store (Feast) for feature management
├─ CI/CD automation with GitHub Actions
├─ Kubernetes deployment with auto-scaling
├─ Comprehensive monitoring & alerting
├─ API with sub-100ms latency
├─ 87% test coverage
└─ Documentation and runbooks

📚 TECHNOLOGIES USED:
├─ ML: XGBoost, PyTorch, scikit-learn
├─ Data: DVC, Feast, BigQuery, S3
├─ DevOps: Docker, Kubernetes, GitHub Actions
├─ Monitoring: Prometheus, Grafana, AlertManager
├─ Infrastructure: AWS/GCP, Minikube
└─ Tracking: MLflow, Weights & Biases

🎓 KEY LEARNINGS:
├─ Training-serving skew is real and costly (prevented with Feature Store)
├─ Data quality >> model complexity (spent 40% time on data)
├─ Monitoring is as important as accuracy (caught 3 data issues early)
├─ Automation saves time and reduces errors (1h CI/CD vs 1 day manual)
├─ Documentation matters (saved onboarding time from days to hours)
└─ Test everything: unit, integration, end-to-end, load tests

⚠️ CHALLENGES & SOLUTIONS:
├─ Challenge: Model retraining time (30 min)
   Solution: Parallel training, cached features → 15 min
│
├─ Challenge: Feature staleness in online store
   Solution: Streaming updates via Kafka → real-time freshness
│
├─ Challenge: P99 latency spikes (1.5s)
   Solution: Model quantization, caching → stable 250ms
│
└─ Challenge: Team collaboration on features
   Solution: Feature Store registry → single source of truth
```

---

## 🚀 FUTURE IMPROVEMENTS (1-2 минуты)

### Слайд 15: Roadmap

```
SHORT TERM (1-2 months):
├─ Add weather forecast features (predict future delays)
├─ Implement active learning (retrain on hard examples)
├─ Add model explainability (SHAP values)
└─ Expand to other airlines

MEDIUM TERM (3-6 months):
├─ Multi-model ensemble (add more diverse architectures)
├─ Real-time model adaptation (concept drift handling)
├─ Customer API with rate limiting & authentication
└─ Mobile app integration

LONG TERM (6-12 months):
├─ Recommendation system (suggest best alternative flights)
├─ Dynamic pricing integration
├─ Federated learning across airlines
└─ Real-time airport status predictions

TECHNICAL DEBT:
├─ [ ] Migrate to managed Feature Store (Hopsworks)
├─ [ ] Add model lineage tracking (Marooqa, DVC)
├─ [ ] Set up data governance (OpenMetadata)
├─ [ ] Implement A/B testing framework
└─ [ ] Add GraphQL API layer

NICE-TO-HAVES:
├─ [ ] Web dashboard for airlines
├─ [ ] Batch prediction API for offline analysis
├─ [ ] Feature attribution analysis
└─ [ ] Cost optimization (reduce inference latency further)
```

---

## ❓ Q&A PREPARATION

### Возможные вопросы от комиссии:

**Q1: Почему вы выбрали XGBoost + NN ensemble, а не что-то более простое?**
```
A: XGBoost хорош для interpretability и быстрого обучения (5 мин).
   NN лучше ловит нелинейные зависимости (20 мин).
   Ensemble дает лучший результат (11.5 vs 12.3 MAE).
   Trade-off: +100ms inference но +3% accuracy.
   В production это окупается (500K сбережений).
```

**Q2: Как вы справляетесь с data drift?**
```
A: Мониторим PSI, KS-statistic еженедельно.
   Пороги: Warning при PSI>0.1, Alert при PSI>0.25.
   Trigger: автоматический ретрейн если drift обнаружен.
   Версионирование: старую модель держим для fallback.
```

**Q3: Почему Feature Store нужен для такого проекта?**
```
A: Без FS: одна фича переписана 3 раза в разных местах.
   Проблемы: training-serving skew, дублирование, slow onboarding.
   С FS: одна трансформация, point-in-time correct, unit tested.
   Benefit: 10x faster to add new model, 0 conflicts.
```

**Q4: Как вы обеспечиваете воспроизводимость?**
```
A: DVC: версионирует данные, трансформации, гиперпараметры.
   MLflow: трекирует метрики, параметры, артефакты.
   Seed: фиксируем random_state везде (numpy, sklearn, torch).
   Docker: идентичное окружение в dev, staging, prod.
   Результат: любой может воспроизвести модель v2.1.0 в любой момент.
```

**Q5: Чем ваш подход к мониторингу отличается от simple metrics tracking?**
```
A: Simple metrics: только accuracy на test set (static).
   Наш подход:
   - Production metrics: real RPS, latency, error rate
   - Data quality: staleness, drift, null rate
   - Correlation: если feature drift → model accuracy drop
   - Alerts: автоматические при аномалиях
   - Dashboard: real-time visibility для team
   Результат: 0 production incidents за 3 месяца.
```

**Q6: Какую самую сложную задачу вы решили?**
```
A: Проблема: P99 latency 1.5s, SLA 500ms.
   Диагностика: profiling показал model.predict = 1000ms.
   Решение 1: Model quantization (float32 → int8) → 600ms.
   Решение 2: Batch feature caching (Redis) → 400ms inference.
   Решение 3: Async processing для batch predictions.
   Результат: P99 latency стабильно 250ms, экономия $100K/year.
```

---

## 📑 ПРЕЗЕНТАЦИОННЫЕ МАТЕРИАЛЫ

Файлы для демонстрации:
```
├─ presentation.pdf (или Google Slides)
│  ├─ Architecture diagram
│  ├─ Model performance metrics
│  ├─ CI/CD pipeline visualization
│  ├─ Monitoring dashboards
│  └─ Business impact
│
├─ demo-commands.sh (все команды для live demo)
│
├─ README.md (в репозитории)
│  ├─ Quick start
│  ├─ Architecture
│  ├─ How to contribute
│  └─ Monitoring & Alerts
│
└─ docs/
   ├─ DEPLOYMENT.md (как развернуть)
   ├─ MONITORING.md (как мониторить)
   ├─ FEATURE_STORE.md (как добавить фичу)
   └─ TROUBLESHOOTING.md (что делать если сломалось)
```

---

## ⏱️ TIMELINE ПРЕЗЕНТАЦИИ

```
Всего: ~30 минут

0-2 мин:    Введение + контекст
2-6 мин:    Архитектура + data
6-10 мин:   Feature Engineering + моделирование
10-15 мин:  CI/CD + Deployment
15-18 мин:  Feature Store + Monitoring
18-22 мин:  API + Results
22-25 мин:  Challenges & Learnings
25-30 мин:  Q&A

Live Demo (параллельно, 5-10 мин):
├─ Запустить API локально
├─ Отправить prediction request
├─ Показать Grafana dashboard
├─ Triggered load test и HPA scaling
└─ Открыть GitHub Actions CI/CD logs
```

---

## 🎯 EVALUATION CRITERIA

Комиссия будет оценивать:

| Критерий | Оценка | Комментарии |
|----------|--------|-----------|
| **Архитектура** | 40% | End-to-end система, best practices |
| **Качество кода** | 25% | Testing, documentation, CI/CD |
| **Результаты** | 20% | Accuracy, performance, reliability |
| **Презентация** | 15% | Ясность, демонстрация, ответы |

**Критерии отличной защиты:**
- ✅ Система работает (не только слайды, а живая демонстрация)
- ✅ Код clean и well-tested (>85% coverage)
- ✅ Production-ready (мониторинг, логирование, graceful shutdown)
- ✅ Масштабируемая (HPA, load testing results)
- ✅ Документирована (README, runbooks, architecture diagrams)
- ✅ Глубокое понимание (может объяснить любую часть)

---

## 📌 ФИНАЛЬНЫЕ СОВЕТЫ

1. **Подготовка к демо:**
   - Все сценарии протестировать заранее
   - Иметь скрипт для быстрого восстановления если что-то сломается
   - Backup: скриншоты и видео на случай технических сбоев

2. **Во время презентации:**
   - Начните с высокого уровня (архитектура), потом в детали
   - Используйте визуали: диаграммы, графики, live dashboards
   - Говорите про бизнес-импакт, не только про технологию
   - Будьте готовы к technical questions

3. **После презентации:**
   - Поделитесь репозиторием (сделайте его публичным с примерами)
   - Оставьте контактную информацию для follow-up questions
   - Предложите to deploy в их environment при необходимости

---

*Успешной защиты! 🎓*
