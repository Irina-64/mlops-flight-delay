# Лабораторная 11: Мониторинг (Prometheus + Grafana) и метрики приложения

## Цель работы
Инструментировать сервис flight-delay-api метриками Prometheus, настроить Prometheus для сбора метрик и Grafana для визуализации, включить alerting.

## Требования
- prometheus_client (Python библиотека)
- Prometheus v2.40+
- Grafana v9.0+
- Docker и Docker Compose (или Kubernetes)
- flight-delay-api с Flask/FastAPI (из ЛР6-10)
- 2+ GB RAM, интернет для загрузки образов

---

## Раздел 1: Внедрение prometheus_client в API

### 1.1. Установка зависимостей

```bash
# Добавить в requirements.txt
pip install prometheus-client==0.19.0 flask==2.3.0
```

### 1.2. Инструментирование src/api.py (полный пример)

Создать/обновить файл `src/api.py`:

```python
from flask import Flask, request, jsonify
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CollectorRegistry
import time
import pickle
import numpy as np
from werkzeug.exceptions import HTTPException

app = Flask(__name__)

# ============ PROMETHEUS МЕТРИКИ ============

# Метрика 1: Количество запросов по типам (Counter)
REQUEST_COUNT = Counter(
    'flight_delay_api_requests_total',
    'Total requests to API',
    ['method', 'endpoint', 'status']
)

# Метрика 2: Латенси запросов (Histogram)
REQUEST_LATENCY = Histogram(
    'flight_delay_api_request_duration_seconds',
    'Request latency in seconds',
    ['endpoint'],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5)
)

# Метрика 3: Распределение прогнозов задержек (Gauge)
PREDICTION_DISTRIBUTION = Gauge(
    'flight_delay_api_prediction_probability',
    'Probability of flight delay prediction',
    ['prediction_class']
)

# Метрика 4: Ошибки по типам (Counter)
PREDICTION_ERRORS = Counter(
    'flight_delay_api_prediction_errors_total',
    'Total prediction errors',
    ['error_type']
)

# ============ ЗАГРУЗКА МОДЕЛИ ============

try:
    with open('/app/models/flight_delay_model.pkl', 'rb') as f:
        model = pickle.load(f)
    MODEL_LOADED = True
except Exception as e:
    print(f"Ошибка загрузки модели: {e}")
    MODEL_LOADED = False

# ============ ENDPOINTS ============

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return {
        'status': 'ok',
        'service': 'flight-delay-api',
        'model_loaded': MODEL_LOADED
    }, 200

@app.route('/metrics', methods=['GET'])
def metrics():
    """Prometheus metrics endpoint"""
    return generate_latest(), 200, {'Content-Type': 'text/plain; charset=utf-8'}

@app.route('/predict', methods=['POST'])
@REQUEST_LATENCY.labels(endpoint='/predict').time()
def predict():
    """
    Endpoint для прогнозирования задержки рейса
    
    Expected JSON:
    {
        "duration": 50,
        "departure_time": "09:00",
        "days_since": 1,
        "origin": "JFK",
        "destination": "LAX"
    }
    """
    start_time = time.time()
    
    try:
        # Проверка и парсинг JSON
        if not request.is_json:
            PREDICTION_ERRORS.labels(error_type='invalid_json').inc()
            REQUEST_COUNT.labels(method='POST', endpoint='/predict', status=400).inc()
            return {'error': 'Request must be JSON'}, 400
        
        data = request.get_json()
        
        # Валидация полей
        required_fields = ['duration', 'departure_time', 'days_since', 'origin', 'destination']
        if not all(field in data for field in required_fields):
            PREDICTION_ERRORS.labels(error_type='missing_fields').inc()
            REQUEST_COUNT.labels(method='POST', endpoint='/predict', status=400).inc()
            return {'error': f'Missing fields. Required: {required_fields}'}, 400
        
        # Проверка модели
        if not MODEL_LOADED:
            PREDICTION_ERRORS.labels(error_type='model_not_loaded').inc()
            REQUEST_COUNT.labels(method='POST', endpoint='/predict', status=503).inc()
            return {'error': 'Model not loaded'}, 503
        
        # Подготовка признаков (адаптировать под вашу модель)
        features = np.array([[
            data.get('duration', 0),
            int(data.get('departure_time', '00:00').split(':')[0]),
            data.get('days_since', 0),
            hash(data.get('origin', '')) % 100,
            hash(data.get('destination', '')) % 100
        ]])
        
        # Прогноз
        prediction = model.predict(features)[0]
        probability = model.predict_proba(features)[0]
        
        # Обновление метрик распределения прогнозов
        delay_prob = float(probability[1]) if len(probability) > 1 else 0.0
        no_delay_prob = float(probability[0]) if len(probability) > 0 else 0.0
        
        PREDICTION_DISTRIBUTION.labels(prediction_class='delay').set(delay_prob)
        PREDICTION_DISTRIBUTION.labels(prediction_class='no_delay').set(no_delay_prob)
        
        # Счётчик успешных запросов
        REQUEST_COUNT.labels(method='POST', endpoint='/predict', status=200).inc()
        
        return {
            'prediction': int(prediction),
            'prediction_label': 'Delay' if prediction == 1 else 'No Delay',
            'probability': {
                'no_delay': float(no_delay_prob),
                'delay': float(delay_prob)
            },
            'processing_time_ms': round((time.time() - start_time) * 1000, 2)
        }, 200
    
    except Exception as e:
        PREDICTION_ERRORS.labels(error_type='internal_error').inc()
        REQUEST_COUNT.labels(method='POST', endpoint='/predict', status=500).inc()
        return {'error': str(e)}, 500

@app.errorhandler(HTTPException)
def handle_exception(e):
    """Обработчик для других HTTP ошибок"""
    REQUEST_COUNT.labels(method=request.method, endpoint=request.path, status=e.code).inc()
    return {'error': e.description}, e.code

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9696, debug=False)
```

### 1.3. Проверка метрик локально

```bash
# Запустить API
python src/api.py &

# Отправить тестовый запрос
curl -X POST "http://localhost:9696/predict" \
  -H "Content-Type: application/json" \
  -d '{"duration":50, "departure_time":"09:00", "days_since":1, "origin":"JFK", "destination":"LAX"}'

# Проверить метрики
curl http://localhost:9696/metrics | head -30
# flight_delay_api_requests_total{endpoint="/predict", method="POST", status="200"} 1.0
# flight_delay_api_request_duration_seconds_bucket{endpoint="/predict", le="0.1"} 1.0
```

---

## Раздел 2: Настройка Prometheus

### 2.1. Создать директорию prometheus/

```bash
mkdir -p prometheus
mkdir -p alertmanager
mkdir -p grafana/provisioning/datasources
mkdir -p grafana/provisioning/dashboards
```

### 2.2. Создать prometheus.yml

Файл `prometheus/prometheus.yml`:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s
  external_labels:
    cluster: 'minikube'
    environment: 'lab11'

scrape_configs:
  # Prometheus сам себя
  - job_name: 'prometheus'
    scrape_interval: 5s
    static_configs:
      - targets: ['localhost:9090']

  # Flight Delay API
  - job_name: 'flight-delay-api'
    scrape_interval: 10s
    metrics_path: '/metrics'
    static_configs:
      - targets: ['flight-delay-svc:80']
        labels:
          service: 'flight-delay-api'
          namespace: 'default'

# Alert Rules
rule_files:
  - '/etc/prometheus/alert_rules.yml'

alerting:
  alertmanagers:
    - static_configs:
        - targets:
            - alertmanager:9093
```

### 2.3. Создать alert_rules.yml

Файл `prometheus/alert_rules.yml`:

```yaml
groups:
- name: flight-delay-api
  interval: 30s
  rules:
  # Alert 1: Высокая латенси
  - alert: HighLatency
    expr: histogram_quantile(0.95, rate(flight_delay_api_request_duration_seconds_bucket[5m])) > 1.0
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "High API latency detected"
      description: "95th percentile latency is > 1s (current: {{ $value }}s)"

  # Alert 2: Высокий процент ошибок
  - alert: HighErrorRate
    expr: rate(flight_delay_api_prediction_errors_total[5m]) / rate(flight_delay_api_requests_total[5m]) > 0.05
    for: 5m
    labels:
      severity: critical
    annotations:
      summary: "High error rate"
      description: "Error rate > 5% (current: {{ $value | humanizePercentage }})"

  # Alert 3: Модель не загружена
  - alert: ModelNotLoaded
    expr: flight_delay_api_requests_total{status="503"} > 0
    for: 1m
    labels:
      severity: critical
    annotations:
      summary: "Model not loaded"
      description: "API returning 503 errors - model load failure"
```

---

## Раздел 3: Запуск Prometheus и Grafana через Docker Compose

### 3.1. Создать docker-compose.yml

Файл `docker-compose.yml` в корне проекта:

```yaml
version: '3.8'

services:
  # ===== PROMETHEUS =====
  prometheus:
    image: prom/prometheus:latest
    container_name: prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - ./prometheus/alert_rules.yml:/etc/prometheus/alert_rules.yml:ro
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.console.libraries=/usr/share/prometheus/console_libraries'
      - '--web.console.templates=/usr/share/prometheus/consoles'
      - '--web.enable-lifecycle'
    networks:
      - monitoring
    restart: unless-stopped

  # ===== GRAFANA =====
  grafana:
    image: grafana/grafana:latest
    container_name: grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_USER=admin
      - GF_SECURITY_ADMIN_PASSWORD=admin123
      - GF_USERS_ALLOW_SIGN_UP=false
      - GF_INSTALL_PLUGINS=grafana-piechart-panel
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning:ro
    depends_on:
      - prometheus
    networks:
      - monitoring
    restart: unless-stopped

  # ===== ALERTMANAGER =====
  alertmanager:
    image: prom/alertmanager:latest
    container_name: alertmanager
    ports:
      - "9093:9093"
    volumes:
      - ./alertmanager/alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro
      - alertmanager_data:/alertmanager
    command:
      - '--config.file=/etc/alertmanager/alertmanager.yml'
      - '--storage.path=/alertmanager'
    networks:
      - monitoring
    restart: unless-stopped

volumes:
  prometheus_data:
  grafana_data:
  alertmanager_data:

networks:
  monitoring:
    driver: bridge
```

### 3.2. Запуск Docker Compose

```bash
# Перейти в корень проекта
cd mlops-flight-delay

# Запустить все сервисы
docker-compose up -d

# Проверить статус
docker-compose ps
# CONTAINER ID   IMAGE              STATUS          PORTS
# xxxx           prom/prometheus    Up 2 minutes    0.0.0.0:9090->9090/tcp
# xxxx           grafana/grafana    Up 2 minutes    0.0.0.0:3000->3000/tcp
# xxxx           prom/alertmanager  Up 2 minutes    0.0.0.0:9093->9093/tcp
```

### 3.3. Структура файлов после подготовки

```
mlops-flight-delay/
├── src/
│   └── api.py                          # С инструментацией Prometheus
├── prometheus/
│   ├── prometheus.yml                   # Конфиг Prometheus
│   └── alert_rules.yml                  # Правила алертов
├── grafana/
│   └── provisioning/
│       ├── datasources/
│       │   └── prometheus.yml           # Datasource подключение
│       └── dashboards/
│           └── flight-delay-dashboard.json
├── alertmanager/
│   └── alertmanager.yml                 # Конфиг Alertmanager
├── docker-compose.yml                   # Docker Compose
├── requirements.txt                     # prometheus-client в зависимостях
└── k8s/
    ├── deployment.yaml
    ├── service.yaml
    └── hpa.yaml
```

---

## Раздел 4: Настройка Grafana

### 4.1. Grafana datasource provisioning

Файл `grafana/provisioning/datasources/prometheus.yml`:

```yaml
apiVersion: 1

datasources:
- name: Prometheus
  type: prometheus
  access: proxy
  url: http://prometheus:9090
  isDefault: true
  editable: true
```

### 4.2. Проверка Prometheus targets

1. Открыть браузер: **http://localhost:9090**
2. Перейти в **Status → Targets**
3. Проверить статус:
   - `prometheus` → UP
   - `flight-delay-api` → UP (если API запущён)

```bash
# Или проверить через curl
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | {job_name: .labels.job, health: .health}'
```

### 4.3. Вход в Grafana

1. Открыть: **http://localhost:3000**
2. Логин: `admin`
3. Пароль: `admin123`
4. Изменить пароль (опционально)

### 4.4. Создание Dashboard в Grafana UI

**Способ 1: Вручную через UI**

1. **Home → Create → Dashboard**
2. **Add panel**
3. Выбрать Prometheus datasource
4. Добавить PromQL запросы:

**Panel 1: Requests Per Second**
```promql
rate(flight_delay_api_requests_total[1m])
```
- Legend: `{{method}} {{endpoint}} {{status}}`
- Type: Graph

**Panel 2: Request Latency (Percentiles)**
```promql
histogram_quantile(0.50, rate(flight_delay_api_request_duration_seconds_bucket[5m]))
histogram_quantile(0.95, rate(flight_delay_api_request_duration_seconds_bucket[5m]))
histogram_quantile(0.99, rate(flight_delay_api_request_duration_seconds_bucket[5m]))
```
- Legend: `p50`, `p95`, `p99`
- Type: Graph

**Panel 3: Prediction Distribution**
```promql
flight_delay_api_prediction_probability
```
- Legend: `{{prediction_class}}`
- Type: Gauge

**Panel 4: Error Rate**
```promql
rate(flight_delay_api_prediction_errors_total[5m])
```
- Legend: `{{error_type}}`
- Type: Graph

**Panel 5: HTTP Status Codes**
```promql
rate(flight_delay_api_requests_total[5m])
```
- Legend: `{{status}}`
- Type: Stacked graph

5. **Save Dashboard** с именем `Flight Delay API Monitoring`

### 4.5. Dashboard JSON (опционально)

Файл `grafana/provisioning/dashboards/flight-delay-dashboard.json`:

```json
{
  "dashboard": {
    "title": "Flight Delay API Monitoring",
    "tags": ["flight-delay", "api", "mlops", "lab11"],
    "timezone": "browser",
    "panels": [
      {
        "id": 1,
        "title": "Requests Per Second",
        "targets": [
          {
            "expr": "rate(flight_delay_api_requests_total[1m])"
          }
        ],
        "type": "timeseries"
      },
      {
        "id": 2,
        "title": "Request Latency (Percentiles)",
        "targets": [
          {"expr": "histogram_quantile(0.50, rate(flight_delay_api_request_duration_seconds_bucket[5m]))"},
          {"expr": "histogram_quantile(0.95, rate(flight_delay_api_request_duration_seconds_bucket[5m]))"},
          {"expr": "histogram_quantile(0.99, rate(flight_delay_api_request_duration_seconds_bucket[5m]))"} 
        ],
        "type": "timeseries"
      },
      {
        "id": 3,
        "title": "Prediction Distribution",
        "targets": [
          {
            "expr": "flight_delay_api_prediction_probability"
          }
        ],
        "type": "gauge"
      },
      {
        "id": 4,
        "title": "Error Rate",
        "targets": [
          {
            "expr": "rate(flight_delay_api_prediction_errors_total[5m])"
          }
        ],
        "type": "timeseries"
      }
    ]
  }
}
```

---

## Раздел 5: Демонстрация мониторинга под нагрузкой

### 5.1. Запустить API (если в контейнере)

```bash
# Если API запущён локально
python src/api.py &

# Если в Docker
docker run -p 9696:9696 flight-delay-api:lab10 &

# Проверить health
curl http://localhost:9696/health
```

### 5.2. Нагрузить API (много запросов)

```bash
# Установить hey (если нет)
go install github.com/rakyll/hey@latest

# Нагрузить /predict на 5000 запросов, 50 параллельных соединений
hey -n 5000 -c 50 -m POST \
  "http://localhost:9696/predict" \
  -H "Content-Type: application/json" \
  -d '{
    "duration": 50,
    "departure_time": "09:00",
    "days_since": 1,
    "origin": "JFK",
    "destination": "LAX"
  }' &

# Процесс пойдёт в фон (~1-2 минуты)
```

### 5.3. Мониторить в реальном времени

```bash
# Открыть Grafana в браузере
# http://localhost:3000/d/flight-delay

# Следить за графиками:
# - Requests/sec: должны расти 10-100 req/s
# - Latency: должна расти (p95 > 100ms)
# - Error Rate: должна оставаться 0% (если API работает)
```

### 5.4. Вызвать ошибки (для проверки error rate)

```bash
# Отправить неправильный JSON
curl -X POST "http://localhost:9696/predict" \
  -H "Content-Type: application/json" \
  -d '{invalid json}' \
  -v

# Отправить без обязательных полей (10 раз)
for i in {1..10}; do
  curl -X POST "http://localhost:9696/predict" \
    -H "Content-Type: application/json" \
    -d '{}'
done

# Error Rate в Grafana должен возрасти
```

### 5.5. Проверить алерты

1. Открыть **http://localhost:9090/alerts**
2. Смотреть статус алертов:
   - Если latency > 1s → Alert: HighLatency (FIRING)
   - Если error_rate > 5% → Alert: HighErrorRate (FIRING)

---

## Раздел 6: Развёртывание в Kubernetes (опционально)

### 6.1. ConfigMap для Prometheus

Файл `k8s/prometheus-config.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: prometheus-config
  namespace: default
data:
  prometheus.yml: |
    global:
      scrape_interval: 15s
    scrape_configs:
    - job_name: 'prometheus'
      static_configs:
      - targets: ['localhost:9090']
    
    - job_name: 'flight-delay-api'
      kubernetes_sd_configs:
      - role: pod
      relabel_configs:
      - source_labels: [__meta_kubernetes_pod_label_app]
        action: keep
        regex: flight-delay-api
      - source_labels: [__meta_kubernetes_pod_port_name]
        action: keep
        regex: http
```

### 6.2. Deployment Prometheus

Файл `k8s/prometheus-deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: prometheus
spec:
  replicas: 1
  selector:
    matchLabels:
      app: prometheus
  template:
    metadata:
      labels:
        app: prometheus
    spec:
      containers:
      - name: prometheus
        image: prom/prometheus:latest
        ports:
        - containerPort: 9090
        volumeMounts:
        - name: config
          mountPath: /etc/prometheus
      volumes:
      - name: config
        configMap:
          name: prometheus-config
---
apiVersion: v1
kind: Service
metadata:
  name: prometheus-svc
spec:
  selector:
    app: prometheus
  ports:
  - port: 9090
  type: NodePort
```

### 6.3. Развернуть в K8s

```bash
# Применить конфиги
kubectl apply -f k8s/prometheus-config.yaml
kubectl apply -f k8s/prometheus-deployment.yaml

# Проверить
kubectl get pods | grep prometheus
kubectl get svc | grep prometheus

# Доступ
minikube service prometheus-svc --url
```

---

## Раздел 7: Alertmanager (опционально)

### 7.1. Создать alertmanager.yml

Файл `alertmanager/alertmanager.yml`:

```yaml
global:
  resolve_timeout: 5m

route:
  receiver: 'default'
  group_by: ['alertname', 'cluster']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 12h
  
  routes:
  - match:
      severity: critical
    receiver: 'critical'
    continue: true

receivers:
- name: 'default'
  webhook_configs:
  - url: 'http://webhook-receiver:5000/alert'

- name: 'critical'
  email_configs:
  - to: 'admin@example.com'
    from: 'alertmanager@example.com'
    smarthost: 'smtp.example.com:587'
    auth_username: 'alertmanager'
    auth_password: 'password'
```

### 7.2. Проверить алерты

```bash
# Открыть Prometheus Alerts
http://localhost:9090/alerts

# Открыть Alertmanager
http://localhost:9093
```

---

## Артефакты и критерии оценки

### Артефакты

| Файл/Компонент | Описание | Статус |
|----------------|---------|--------|
| **src/api.py** | API с prometheus_client метриками | ☐ |
| **prometheus/prometheus.yml** | Конфиг Prometheus с targets | ☐ |
| **prometheus/alert_rules.yml** | Правила алертов | ☐ |
| **docker-compose.yml** | Запуск Prometheus, Grafana, Alertmanager | ☐ |
| **grafana/provisioning/datasources/** | Автопровижионирование Prometheus | ☐ |
| **grafana/provisioning/dashboards/** | Dashboard с графиками | ☐ |

### Критерии оценки

✅ **Метрики экспортируются:**
```bash
curl http://localhost:9696/metrics | grep flight_delay_api
# flight_delay_api_requests_total{...} N
# flight_delay_api_request_duration_seconds_bucket{...} N
# flight_delay_api_prediction_probability{...} N
```

✅ **Prometheus скрэйпит метрики:**
```bash
# http://localhost:9090/targets
# flight-delay-api → UP
```

✅ **Grafana отображает данные:**
- Dashboard видна в http://localhost:3000
- Графики показывают метрики в реальном времени
- Легенды корректны

✅ **Алерты работают:**
- http://localhost:9090/alerts показывает статус
- При нагрузке алерты переходят в FIRING

### Проверочный чек-лист

| Задача | Команда/URL | Результат | ☑ |
|--------|-------------|-----------|---|
| Метрики API | `curl localhost:9696/metrics` | flight_delay_api_* видны | ☐ |
| Prometheus targets | http://localhost:9090/targets | flight-delay-api UP | ☐ |
| Grafana datasource | http://localhost:3000/datasources | Prometheus подключен | ☐ |
| Dashboard создан | http://localhost:3000/d/flight-delay | 5 панелей видны | ☐ |
| Запросы/сек | График растет при нагрузке | rps > 10 | ☐ |
| Latency p95 | На графике видна | > 10ms | ☐ |
| Error rate | Остаётся 0% без ошибок | 0% при успехе | ☐ |
| Алерты | http://localhost:9090/alerts | HighLatency, HighErrorRate | ☐ |

---

## Дополнительные ресурсы

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/grafana/latest/)
- [prometheus_client Python](https://github.com/prometheus/client_python)
- [PromQL Querying](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [Alertmanager](https://prometheus.io/docs/alerting/latest/overview/)

---

**✅ Лабораторная 11 завершена!** flight-delay-api теперь полностью инструментирована и мониторится в реальном времени с помощью Prometheus и Grafana.
