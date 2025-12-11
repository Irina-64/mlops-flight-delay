# 📋 ВСЕ ФАЙЛЫ, УПОМИНАЕМЫЕ В defense_guide.md

**Из документа "Защита проекта: Система предсказания задержек рейсов"**

---

## 📊 СТАТИСТИКА

- **Всего файлов:** 49
- **Категорий:** 10
- **Директорий:** 12

---

## 🎯 ПРЕЗЕНТАЦИОННЫЕ МАТЕРИАЛЫ

Файлы, необходимые для защиты проекта перед комиссией.

| Файл | Описание | Статус |
|------|---------|--------|
| `presentation.pdf` | Презентация (или Google Slides) для защиты | 📄 |
| `demo-commands.sh` | Все команды для live demo | 🔧 |
| `README.md` | Основная документация репозитория | 📖 |
| `docs/DEPLOYMENT.md` | Инструкция по развертыванию системы | 🚀 |
| `docs/MONITORING.md` | Как мониторить и отслеживать систему | 📊 |
| `docs/FEATURE_STORE.md` | Руководство по работе с Feature Store | 🔌 |
| `docs/TROUBLESHOOTING.md` | Решение проблем и FAQ | 🔍 |

---

## 💻 ИСХОДНЫЙ КОД (src/)

Python скрипты для основной логики приложения.

| Файл | Назначение |
|------|-----------|
| `src/preprocess.py` | Предобработка данных (очистка, нормализация) |
| `src/feature_eng.py` | Feature engineering (создание признаков) |
| `src/train.py` | Обучение моделей (XGBoost + Neural Network) |
| `src/evaluate.py` | Оценка моделей (метрики, валидация) |
| `src/api.py` | REST API на FastAPI для инференса |
| `src/eda.py` | Exploratory Data Analysis (визуализация) |

---

## 🔄 DVC PIPELINE (Data Version Control)

Файлы для воспроизводимого ML pipeline.

| Файл | Описание |
|------|---------|
| `dvc.yaml` | Определение stages pipeline (preprocessing, training, evaluation) |
| `dvc.lock` | Frozen dependencies (хеши данных, параметры, выходы) |
| `.dvc/config` | Конфигурация DVC (remote storage, cache settings) |

**Пример dvc.yaml:**
```yaml
stages:
  preprocess:
    cmd: python src/preprocess.py
    deps:
      - src/preprocess.py
      - data/raw/
    outs:
      - data/processed/
  
  feature_engineering:
    cmd: python src/feature_eng.py
    deps:
      - src/feature_eng.py
      - data/processed/
    outs:
      - data/featured/
  
  train:
    cmd: python src/train.py
    deps:
      - src/train.py
      - data/featured/
    outs:
      - models/model.pkl
    metrics:
      - reports/metrics.json
```

---

## 🌟 FEATURE STORE (Feast)

Управление и версионирование признаков для ML моделей.

| Файл | Описание |
|------|---------|
| `feature_store.yaml` | Конфигурация Feature Store (project, provider, stores) |
| `features/route_features.py` | Признаки маршрутов (avg_delay_7d, on_time_pct, volume) |
| `features/airline_features.py` | Признаки авиакомпаний (reliability, delay_history) |
| `features/temporal_features.py` | Временные признаки (hour, day_of_week, season) |

**Пример feature_store.yaml:**
```yaml
project: flight-delay
provider: local  # or gcp, aws
offline_store:
  type: bigquery
  dataset: flight_delay_features
online_store:
  type: redis
  connection_string: redis://localhost:6379
entity_key_serialization_version: 2
```

---

## ☸️ KUBERNETES КОНФИГУРАЦИЯ (k8s/)

Манифесты для развертывания в production на Kubernetes.

### Основные манифесты:

| Файл | Назначение |
|------|-----------|
| `k8s/deployment.yaml` | Развертывание подов (replicas, resources, probes) |
| `k8s/service.yaml` | LoadBalancer/NodePort сервис для API |
| `k8s/hpa.yaml` | Horizontal Pod Autoscaler (масштабирование) |
| `k8s/configmap.yaml` | ConfigMap для env variables и конфигов |

### Дополнительные ресурсы (k8s/resources/):

| Файл | Назначение |
|------|-----------|
| `k8s/resources/network-policy.yaml` | NetworkPolicy для ограничения трафика |
| `k8s/resources/pod-disruption-budget.yaml` | PodDisruptionBudget для высокой доступности |
| `k8s/resources/service-monitor.yaml` | ServiceMonitor для Prometheus мониторинга |

**Пример deployment.yaml:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: flight-delay-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: flight-delay-api
  template:
    metadata:
      labels:
        app: flight-delay-api
    spec:
      containers:
      - name: api
        image: ghcr.io/irina-64/flight-delay-api:latest
        ports:
        - containerPort: 9696
        resources:
          requests:
            cpu: 500m
            memory: 512Mi
          limits:
            cpu: 1000m
            memory: 1Gi
        livenessProbe:
          httpGet:
            path: /health
            port: 9696
          initialDelaySeconds: 30
          periodSeconds: 10
```

---

## 🔄 CI/CD PIPELINE (GitHub Actions)

Автоматизация тестирования и развертывания.

| Файл | Описание |
|------|---------|
| `.github/workflows/ci.yml` | CI pipeline (lint, tests, security scan, build) |
| `.github/workflows/deploy.yml` | CD pipeline (deploy to staging/production) |

**Пример .github/workflows/ci.yml:**
```yaml
name: CI - Test & Build

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
      - run: pip install flake8 black isort mypy
      - run: flake8 src tests
      - run: black --check src tests
      - run: mypy src

  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - run: pip install -r requirements.txt pytest pytest-cov
      - run: pytest tests/ --cov=src --cov-report=xml
      - uses: codecov/codecov-action@v2

  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - run: pip install bandit safety
      - run: bandit -r src/
      - run: safety check

  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - run: docker build -t ghcr.io/irina-64/flight-delay-api:latest .
      - run: docker push ghcr.io/irina-64/flight-delay-api:latest
```

---

## 🐳 DOCKER

Контейнеризация приложения.

| Файл | Описание |
|------|---------|
| `Dockerfile` | Multi-stage Docker образ (builder + runtime) |
| `docker-compose.yml` | Локальное окружение (API, Redis, Grafana, Prometheus) |

**Пример Dockerfile:**
```dockerfile
# Builder stage
FROM python:3.11-slim as builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Runtime stage
FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY src/ ./src/
COPY models/ ./models/

RUN useradd -m appuser
USER appuser

EXPOSE 9696
CMD ["python", "-m", "src.api"]
```

**Пример docker-compose.yml:**
```yaml
version: '3.8'

services:
  api:
    build: .
    ports:
      - "9696:9696"
    environment:
      - REDIS_URL=redis://redis:6379
      - LOG_LEVEL=INFO
    depends_on:
      - redis
      - prometheus

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
```

---

## 🧪 ТЕСТЫ (tests/)

Unit и integration тесты для качества кода.

| Файл | Описание | Coverage |
|------|---------|----------|
| `tests/test_preprocess.py` | Тесты предобработки данных | ✅ |
| `tests/test_api.py` | Тесты REST API endpoints | ✅ |
| `tests/test_model.py` | Тесты загрузки и инференса моделей | ✅ |
| `tests/test_features.py` | Тесты создания признаков (Feature Store) | ✅ |
| `tests/integration/test_e2e.py` | End-to-end тесты (full pipeline) | ✅ |
| `tests/integration/test_drift_detection.py` | Тесты детекции drift в данных | ✅ |

**Цель:** Coverage > 85% (текущий: 87%)

**Пример test_api.py:**
```python
import pytest
from fastapi.testclient import TestClient
from src.api import app

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_predict_endpoint():
    payload = {
        "route": "JFK-LAX",
        "airline": "AA",
        "departure_time": "2024-01-15T14:30:00"
    }
    response = client.post("/predict", json=payload)
    assert response.status_code == 200
    assert "delay_minutes" in response.json()
    assert response.json()["confidence"] > 0.5

def test_predict_endpoint_invalid_input():
    response = client.post("/predict", json={})
    assert response.status_code == 400
```

---

## 🤖 МОДЕЛИ И АРТЕФАКТЫ (models/, reports/)

Сохраненные модели и результаты обучения.

| Файл | Описание | Размер |
|------|---------|--------|
| `models/model.pkl` | Финальная ensemble модель | ~45 MB |
| `models/xgboost_model.pkl` | XGBoost модель | ~45 MB |
| `models/neural_network_model.pt` | PyTorch neural network | ~12 MB |
| `reports/metrics.json` | Метрики обучения (MAE, R², accuracy) | ~5 KB |

**Пример reports/metrics.json:**
```json
{
  "baseline": {
    "mae": 45.3,
    "rmse": 62.1,
    "r2": 0.20
  },
  "xgboost": {
    "mae": 12.3,
    "rmse": 28.5,
    "r2": 0.78,
    "training_time_minutes": 5
  },
  "neural_network": {
    "mae": 11.8,
    "rmse": 27.2,
    "r2": 0.80,
    "training_time_minutes": 20
  },
  "ensemble": {
    "mae": 11.5,
    "rmse": 26.8,
    "r2": 0.81,
    "inference_time_ms": 45
  },
  "accuracy_by_airline": {
    "AA": 10.2,
    "UA": 11.8,
    "DL": 12.1,
    "SW": 13.4
  }
}
```

---

## ⚙️ КОНФИГУРАЦИЯ И ЗАВИСИМОСТИ

Системные и Python зависимости, конфигурация проекта.

| Файл | Описание |
|------|---------|
| `requirements.txt` | Python зависимости (pandas, scikit-learn, xgboost, torch, fastapi, feast и т.д.) |
| `setup.py` или `pyproject.toml` | Конфигурация проекта, версионирование, entry points |
| `.gitignore` | Игнорируемые файлы (models/, __pycache__, .env, .dvc/cache) |
| `.env.example` | Пример переменных окружения (REDIS_URL, LOG_LEVEL, MODEL_PATH) |
| `pytest.ini` | Конфигурация pytest (testpaths, addopts, markers) |
| `.flake8` | Конфигурация linter flake8 (max-line-length, exclude) |
| `.pylintrc` | Конфигурация pylint |
| `mypy.ini` | Конфигурация type checking mypy |
| `Makefile` | Удобные команды (make lint, make test, make deploy) |

**Пример requirements.txt:**
```
# Data
pandas==2.0.3
numpy==1.24.3
scikit-learn==1.3.0

# Models
xgboost==2.0.0
torch==2.0.1
lightgbm==4.0.0

# Feature Store
feast==0.28.0

# API
fastapi==0.100.0
uvicorn==0.23.0
pydantic==2.0.0

# Monitoring & Tracking
prometheus-client==0.17.0
mlflow==2.7.0

# Testing
pytest==7.4.0
pytest-cov==4.1.0
pytest-asyncio==0.21.0

# Code Quality
flake8==6.0.0
black==23.7.0
isort==5.12.0
mypy==1.4.1
bandit==1.7.5

# DVC
dvc==3.23.0

# Others
python-dotenv==1.0.0
```

**Пример Makefile:**
```makefile
.PHONY: install test lint format deploy deploy-minikube clean

install:
	pip install -r requirements.txt

lint:
	flake8 src tests
	pylint src
	mypy src

format:
	black src tests
	isort src tests

test:
	pytest tests/ -v --cov=src --cov-report=html

feature-store:
	feast apply
	feast materialize 2024-01-01 2024-01-31

dvc-train:
	dvc repro

deploy-local:
	docker-compose up -d

deploy-minikube:
	minikube start
	kubectl apply -f k8s/

deploy-k8s:
	kubectl apply -f k8s/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache htmlcov .mypy_cache
```

---

## 📚 ДОКУМЕНТАЦИЯ (docs/)

Подробная документация системы.

| Файл | Содержание |
|------|-----------|
| `docs/ARCHITECTURE.md` | Архитектура системы, диаграммы, компоненты |
| `docs/DEPLOYMENT.md` | Пошаговое развертывание (Docker, K8s, облако) |
| `docs/MONITORING.md` | Мониторинг (Prometheus, Grafana, алерты) |
| `docs/FEATURE_STORE.md` | Работа с Feast (как добавлять фичи, мониторить) |
| `docs/TROUBLESHOOTING.md` | Решение проблем и частые вопросы (FAQ) |

---

## 🌐 ДАННЫЕ (data/)

Примечание: эти файлы НЕ хранятся в репозитории (в .gitignore), а отслеживаются DVC.

```
data/
├── raw/                    # Исходные данные
│   ├── flights_history.csv
│   ├── weather_hourly.csv
│   └── airlines_performance.csv
│
├── processed/              # После обработки
│   ├── flights_processed.parquet
│   ├── weather_processed.parquet
│   └── airlines_processed.parquet
│
└── featured/               # После feature engineering
    └── training_features.parquet
```

---

## 🔗 ССЫЛКИ И РЕСУРСЫ, УПОМИНАЕМЫЕ В ЗАЩИТЕ

### Локальные сервисы (при локальной разработке):

```
http://localhost:9696       # REST API
http://localhost:9696/health
http://localhost:9696/metrics      # Prometheus metrics
http://localhost:3000       # Grafana dashboard (admin/admin)
http://localhost:5000       # MLflow UI
http://localhost:6379       # Redis
http://localhost:9090       # Prometheus
```

### GitHub:

```
https://github.com/irina-64/mlops-flight-delay              # Репозиторий
https://github.com/irina-64/mlops-flight-delay/actions      # CI/CD
https://ghcr.io/irina-64/flight-delay-api:latest             # Docker image
```

### Облачные платформы:

```
AWS: S3 (data), EC2 (compute), SageMaker (ML)
GCP: BigQuery (features), Cloud Run (API), Vertex AI
Azure: ADLS (storage), Container Instances, ML Services
```

---

## 📋 ПОЛНАЯ СТРУКТУРА ПРОЕКТА

```
flight-delay-prediction/
├── .github/
│   └── workflows/
│       ├── ci.yml                 ← GitHub Actions CI
│       └── deploy.yml             ← GitHub Actions CD
│
├── .dvc/
│   └── config                     ← DVC конфигурация
│
├── k8s/                           ← Kubernetes манифесты
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── hpa.yaml
│   ├── configmap.yaml
│   └── resources/
│       ├── network-policy.yaml
│       ├── pod-disruption-budget.yaml
│       └── service-monitor.yaml
│
├── docs/                          ← Документация
│   ├── ARCHITECTURE.md
│   ├── DEPLOYMENT.md
│   ├── MONITORING.md
│   ├── FEATURE_STORE.md
│   └── TROUBLESHOOTING.md
│
├── src/                           ← Исходный код
│   ├── __init__.py
│   ├── preprocess.py
│   ├── feature_eng.py
│   ├── train.py
│   ├── evaluate.py
│   ├── api.py
│   └── eda.py
│
├── features/                      ← Feature Store (Feast)
│   ├── route_features.py
│   ├── airline_features.py
│   └── temporal_features.py
│
├── tests/                         ← Тесты
│   ├── __init__.py
│   ├── test_preprocess.py
│   ├── test_api.py
│   ├── test_model.py
│   ├── test_features.py
│   └── integration/
│       ├── test_e2e.py
│       └── test_drift_detection.py
│
├── models/                        ← Сохраненные модели
│   ├── xgboost_model.pkl
│   ├── neural_network_model.pt
│   └── model.pkl (ensemble)
│
├── reports/                       ← Результаты
│   └── metrics.json
│
├── data/                          ← Данные (tracked by DVC, not in git)
│   ├── raw/
│   ├── processed/
│   └── featured/
│
├── dvc.yaml                       ← DVC pipeline
├── dvc.lock                       ← DVC lock file
├── feature_store.yaml             ← Feast конфигурация
├── Dockerfile                     ← Docker образ
├── docker-compose.yml             ← Локальное окружение
├── requirements.txt               ← Python зависимости
├── setup.py                       ← Setup конфигурация
├── pyproject.toml                 ← Project config (alt. to setup.py)
├── pytest.ini                     ← Pytest конфигурация
├── .flake8                        ← Flake8 конфигурация
├── .pylintrc                      ← Pylint конфигурация
├── mypy.ini                       ← Mypy конфигурация
├── Makefile                       ← Удобные команды
├── .gitignore                     ← Git ignore rules
├── .env.example                   ← Пример env variables
├── README.md                      ← Main documentation
├── LICENSE                        ← Лицензия
└── CONTRIBUTING.md                ← Гайд для контрибьютеров
```

---

## ✨ ИТОГО

| Категория | Кол-во файлов |
|-----------|---------------|
| Презентационные материалы | 7 |
| Исходный код | 6 |
| DVC pipeline | 3 |
| Feature Store | 4 |
| Kubernetes | 7 |
| CI/CD | 2 |
| Docker | 2 |
| Тесты | 6 |
| Модели и артефакты | 4 |
| Конфигурация | 8 |
| **ВСЕГО** | **49** |

---

**Все файлы упоминаются в defense_guide.md для полной защиты проекта!** 🎓
