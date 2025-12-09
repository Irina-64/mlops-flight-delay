# Лабораторная 10: Деплой в Kubernetes (Minikube)

## Цель работы
Развернуть API контейнер в локальном Kubernetes (Minikube) и обеспечить масштабирование с использованием HorizontalPodAutoscaler.

## Требования
- Docker Desktop или Docker CE
- Minikube v1.30+
- kubectl v1.28+
- flight-delay-api Dockerfile (из ЛР6)
- 2-4 GB RAM, 2+ CPU ядра

---

## Раздел 1: Подготовка окружения Minikube

### 1.1. Установка необходимых компонентов

#### Docker Desktop (или Docker CE):
```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# macOS/Windows — Docker Desktop из официального сайта
```

#### Minikube:
```bash
# Ubuntu/macOS
curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64
sudo install minikube-linux-amd64 /usr/local/bin/minikube

# Windows — chocolatey или скачивание exe
```

#### kubectl:
```bash
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install kubectl /usr/local/bin/kubectl
```

### 1.2. Проверка установки

```bash
# Docker
docker --version
docker run hello-world

# Minikube
minikube version

# kubectl
kubectl version --client
```

### 1.3. Запуск Minikube и настройка Docker-контекста

```bash
# Запуск Minikube (первый запуск ~5-10 мин)
minikube start --driver=docker --cpus=2 --memory=4096

# Проверка статуса
minikube status

# Переключение Docker на Minikube (КРИТИЧЕСКИ ВАЖНО!)
eval $(minikube docker-env)

# Проверка — Docker должен показывать minikube context
docker context ls
docker info | grep Name  # должно быть minikube
```

### 1.4. Таблица требований и статусов

| Компонент | Требование | Команда проверки | ✅ Готово |
|-----------|------------|------------------|----------|
| Docker | v20+ | `docker --version` | ☐ |
| Minikube | v1.30+ | `minikube version` | ☐ |
| kubectl | v1.28+ | `kubectl version --client` | ☐ |
| Minikube запущен | Running | `minikube status` | ☐ |
| Docker в Minikube | minikube context | `docker context ls` | ☐ |

---

## Раздел 2: Сборка Docker образа внутри Minikube

### 2.1. Запуск и проверка Minikube

```bash
# 2.1.1. Запустить Minikube (если не запущен)
minikube start --driver=docker --cpus=2 --memory=4096mb

# 2.1.2. Проверить статус
minikube status
# Должно быть: host: Running, kubelet: Running, apiserver: Running

# 2.1.3. Открыть dashboard (опционально, для визуального контроля)
minikube dashboard
```

### 2.2. Переключение Docker контекста на Minikube

```bash
# 2.2.1. Активировать Docker среду Minikube (КРИТИЧЕСКИ ВАЖНО!)
eval $(minikube docker-env)

# 2.2.2. Проверить переключение контекста
docker context ls
# Активный контекст должен быть: * minikube

# 2.2.3. Проверить Docker info
docker info | grep -i "name\|server"
# Docker Server: minikube

# 2.2.4. Проверить, куда идут образы
docker images
# Пока пусто или только базовые образы minikube
```

### 2.3. Подготовка проекта mlops-flight-delay

```bash
# 2.3.1. Клонировать/перейти в проект
cd ~/mlops-flight-delay  # или git clone https://github.com/Irina-64/mlops-flight-delay.git

# 2.3.2. Проверить наличие Dockerfile
ls -la Dockerfile* requirements.txt app.py main.py
# Должны быть: Dockerfile, requirements.txt, app.py/main.py

# 2.3.3. Проверить структуру проекта
tree . -L 2  # или find . -name "*.py" -o -name "Dockerfile"
```

### 2.4. Сборка образа внутри Minikube Docker

```bash
# 2.4.1. Собрать образ с тегом lab10 (из корня проекта)
docker build -t flight-delay-api:lab10 .

# 2.4.2. Детальный вывод сборки (если нужно отладить)
docker build --no-cache --progress=plain -t flight-delay-api:lab10 .

# 2.4.3. Проверить успешную сборку
docker images | grep flight-delay-api
# Должно быть: flight-delay-api  lab10  <размер>  <время>
```

### 2.5. Проверка образа в Minikube

```bash
# 2.5.1. Проверить образы в Minikube
minikube image ls | grep flight-delay-api
# Должно показать: flight-delay-api:lab10

# 2.5.2. Проверить образы в кластере
kubectl get pods -n kube-system | grep docker
# Docker daemon Minikube работает

# 2.5.3. Локальный тест контейнера (опционально)
docker run --rm flight-delay-api:lab10 python -c "import flask; print('Flask OK')"
```

### 2.6. Типичные проблемы и решения

| Проблема | Симптом | Решение |
|----------|---------|---------|
| `Cannot connect to the Docker daemon` | Docker context не minikube | `eval $(minikube docker-env)` |
| `Image not found` в подах | Образ не в Minikube Docker | Пересобрать после `eval $(minikube docker-env)` |
| `Build fails: no space left` | Недостаточно RAM/disk | `minikube delete && minikube start --memory=6g --disk-size=30g` |
| `Pull access denied` для base image | Прокси/сетевые проблемы | `minikube ssh "docker pull python:3.9-slim"` заранее |

### 2.7. Финальная проверка готовности к деплою

```bash
echo "=== Docker context ==="
docker context ls | grep '*'

echo "=== Minikube status ==="
minikube status

echo "=== API image ready ==="
docker images flight-delay-api:lab10 --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"

echo "=== Minikube sees image ==="
minikube image ls | grep flight-delay-api

echo "✅ Готово к созданию deployment.yaml!"
```

---

## Раздел 3: Создание манифестов Kubernetes

### 3.1. Создание каталога k8s/

```bash
mkdir -p k8s
cd k8s
```

### 3.2. deployment.yaml

Создать файл `k8s/deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: flight-delay-deployment
  labels:
    app: flight-delay-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: flight-delay-api
  template:
    metadata:
      labels:
        app: flight-delay-api
    spec:
      containers:
      - name: flight-delay-api
        image: flight-delay-api:lab10
        imagePullPolicy: Never
        ports:
        - containerPort: 9696
          name: http
        resources:
          requests:
            memory: "64Mi"
            cpu: "100m"
          limits:
            memory: "128Mi"
            cpu: "500m"
        env:
        - name: MODEL_PATH
          value: "/app/models/flight_delay_model.pkl"
        - name: MLFLOW_TRACKING_URI
          value: "http://localhost:5000"
        livenessProbe:
          httpGet:
            path: /health
            port: 9696
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /predict
            port: 9696
          initialDelaySeconds: 20
          periodSeconds: 5
```

### 3.3. service.yaml

Создать файл `k8s/service.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: flight-delay-svc
  labels:
    app: flight-delay-api
spec:
  type: NodePort
  selector:
    app: flight-delay-api
  ports:
  - port: 80
    targetPort: 9696
    nodePort: 30096
    protocol: TCP
    name: http
```

### 3.4. hpa.yaml

Создать файл `k8s/hpa.yaml`:

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: flight-delay-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: flight-delay-deployment
  minReplicas: 1
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 60
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
      - type: Pods
        value: 2
        periodSeconds: 30
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
      - type: Pods
        value: 1
        periodSeconds: 60
```

### 3.5. Проверка файлов

```bash
# Проверить синтаксис YAML
kubectl apply -f k8s/ --dry-run=client -o yaml

# Должно быть без ошибок
# kubectl apply -f k8s/deployment.yaml --dry-run=client
# kubectl apply -f k8s/service.yaml --dry-run=client
# kubectl apply -f k8s/hpa.yaml --dry-run=client
```

---

## Раздел 4: Применение манифестов и проверка сервиса

### 4.1. Применение манифестов

```bash
# 4.1.1. Применить все манифесты
kubectl apply -f k8s/

# 4.1.2. Проверить все созданные ресурсы
kubectl get all -l app=flight-delay-api
```

### 4.2. Проверка Deployment и подов

```bash
# 4.2.1. Проверить Deployment
kubectl get deployment flight-delay-deployment
# READY 2/2  UP-TO-DATE 2  AVAILABLE 2

# 4.2.2. Проверить поды
kubectl get pods -l app=flight-delay-api
# flight-delay-deployment-xxx-yyy  1/1  Running  0  2m

# 4.2.3. Логи пода (если проблемы)
kubectl logs deployment/flight-delay-deployment

# 4.2.4. Описание пода (детали статуса)
kubectl describe pod <pod-name>
```

### 4.3. Проверка Service

```bash
# 4.3.1. Проверить Service
kubectl get svc flight-delay-svc
# NAME             TYPE       CLUSTER-IP     EXTERNAL-IP   PORT(S)        AGE
# flight-delay-svc NodePort   10.96.123.45   <none>        80:30096/TCP   1m

# 4.3.2. Получить URL сервиса через Minikube
minikube service flight-delay-svc --url
# |-----------|---------------------|-------------|---------------------------|
# | NAMESPACE |       NAME          | TARGET PORT |         URL               |
# | default   | flight-delay-svc    | http/80     | http://192.168.49.2:30096 |

# 4.3.3. Сохранить URL в переменную
export SVC_URL=$(minikube service flight-delay-svc --url | tail -1 | awk '{print $4}')
echo $SVC_URL
```

### 4.4. Тест API

```bash
# 4.4.1. Проверить health endpoint
curl -X GET "$SVC_URL/health"
# {"status": "ok", "service": "flight-delay-api", "model_loaded": true}

# 4.4.2. Отправить тестовый запрос на эндпоинт предсказания
curl -X POST "$SVC_URL/predict" \
  -H "Content-Type: application/json" \
  -d '{
    "duration": 50,
    "departure_time": "09:00",
    "days_since": 1,
    "origin": "JFK",
    "destination": "LAX"
  }'

# 4.4.3. Ожидаемый ответ
# {
#   "prediction": 1,
#   "prediction_label": "Delay",
#   "probability": {
#     "no_delay": 0.35,
#     "delay": 0.65
#   },
#   "processing_time_ms": 12.5
# }
```

### 4.5. Распространённые ошибки и решения

| Проблема | Лог | Решение |
|----------|-----|---------|
| `ImagePullBackOff` | `ErrImagePull` | `imagePullPolicy: Never` + пересобрать в minikube docker |
| `CrashLoopBackOff` | `python: can't open file` | Проверить `MODEL_PATH`, добавить health endpoint |
| `Pending` (HPA не работает) | `FailedGetResourceMetric` | `minikube addons enable metrics-server` |
| `0/1 Ready` | Probe failed | Увеличить `initialDelaySeconds` или добавить `/health` |
| `Connection refused` | curl не отвечает | Проверить `curl -X GET http://localhost:30096/health` напрямую |

---

## Раздел 5: Проверка масштабирования

### 5.1. Включение metrics-server (обязательно!)

```bash
# Включить metrics-server для HPA
minikube addons enable metrics-server

# Проверить, что metrics работают (может занять 30-60 сек)
kubectl get apiservices | grep metrics.k8s.io
# v1beta1.metrics.k8s.io   True
```

### 5.2. Проверка HPA

```bash
# 5.2.1. Проверить статус HPA
kubectl get hpa flight-delay-hpa
# NAME               REFERENCE                           TARGETS   MINPODS   MAXPODS   REPLICAS   AGE
# flight-delay-hpa   flight-delay-deployment/scale       0%/60%    1         10        2          1m

# 5.2.2. Детали HPA
kubectl describe hpa flight-delay-hpa
# Events:
#  Current load: 45% → OK
#  Scaling to 2 pods

# 5.2.3. Метрики подов
kubectl top pods -l app=flight-delay-api
# NAME                               CPU(cores)   MEMORY(bytes)
# flight-delay-deployment-abc-123    45m (45%)    32Mi (25%)
```

### 5.3. Нагрузка и масштабирование

```bash
# 5.3.1. Установить hey (если нет)
go install github.com/rakyll/hey@latest

# 5.3.2. Нагрузить сервис (запустить в фоне)
hey -n 10000 -c 50 -m POST "$SVC_URL/predict" \
  -H "Content-Type: application/json" \
  -d '{
    "duration": 50,
    "departure_time": "09:00",
    "days_since": 1,
    "origin": "JFK",
    "destination": "LAX"
  }' &

# 5.3.3. Следить за масштабированием (новый терминал)
watch -n 5 'kubectl get hpa; echo "---"; kubectl get pods -l app=flight-delay-api'

# Ожидаемый результат:
# 1m → CPU 45% → 2 pods (стабильно)
# 2m → CPU 75% → scaling to 4 pods
# 5m → CPU 55% → stable 4 pods
# 10m (после нагрузки) → CPU 30% → scaling down to 2 pods
```

### 5.4. Вручную изменить количество реплик

```bash
# 5.4.1. Увеличить число реплик (отключает HPA временно)
kubectl scale --replicas=5 deployment/flight-delay-deployment

# 5.4.2. Проверить
kubectl get pods -l app=flight-delay-api
# Должно быть 5 подов

# 5.4.3. Вернуть к HPA управлению
# HPA автоматически вернёт в нормальное состояние
kubectl get hpa flight-delay-hpa
```

---

## Раздел 6: Альтернатива: Port Forward

```bash
# Быстрый доступ без NodePort (для теста)
kubectl port-forward deployment/flight-delay-deployment 9696:9696

# Теперь API доступно на localhost:9696
curl -X POST "http://localhost:9696/predict" \
  -H "Content-Type: application/json" \
  -d '{"duration":50, "departure_time":"09:00", "days_since":1, "origin":"JFK", "destination":"LAX"}'
```

---

## Артефакты и критерии оценки

### Артефакты
- ✅ Каталог `k8s/` в репозитории студента с рабочими манифестами:
  - `deployment.yaml` — управляет подами с API контейнером
  - `service.yaml` — публикует сервис наружу (NodePort)
  - `hpa.yaml` — автоматическое масштабирование по CPU

### Критерии оценки
- ✅ Эндпоинт предсказания доступен и корректно отвечает на запросы
  - `curl "$SVC_URL/predict"` возвращает JSON с прогнозом
- ✅ Количество реплик можно увеличить вручную и/или через HPA
  - `kubectl scale --replicas=5` работает
  - HPA автоматически масштабирует при нагрузке (CPU > 60%)
- ✅ Поды здоровы (все Running, Ready 1/1)
- ✅ Метрики CPU/Memory видны в `kubectl top pods`

### Проверочный чек-лист

| Задача | Команда | Результат | ☑ |
|--------|---------|-----------|---|
| Deployment создан | `kubectl get deployment` | flight-delay-deployment | ☐ |
| 2 пода Running | `kubectl get pods` | 2/2 Running | ☐ |
| Service доступен | `minikube service flight-delay-svc --url` | URL выведен | ☐ |
| API отвечает | `curl $SVC_URL/predict` | JSON с прогнозом | ☐ |
| HPA создана | `kubectl get hpa` | flight-delay-hpa | ☐ |
| Metrics работают | `kubectl top pods` | CPU/Memory видны | ☐ |
| Масштабирование | под нагрузкой replicas > 2 | 4-5 подов | ☐ |

---

## Раздел 7: Опционально — Helm Chart

### 7.1. Создать Helm chart

```bash
# Создать структуру чарта
helm create flight-delay-api

# Структура будет:
# flight-delay-api/
# ├── Chart.yaml
# ├── values.yaml
# ├── templates/
# │   ├── deployment.yaml
# │   ├── service.yaml
# │   ├── hpa.yaml
# │   └── ...
```

### 7.2. Обновить values.yaml

```yaml
# values.yaml
replicaCount: 2
image:
  repository: flight-delay-api
  tag: lab10
  pullPolicy: Never

service:
  type: NodePort
  port: 80
  targetPort: 9696
  nodePort: 30096

resources:
  requests:
    memory: "64Mi"
    cpu: "100m"
  limits:
    memory: "128Mi"
    cpu: "500m"

autoscaling:
  enabled: true
  minReplicas: 1
  maxReplicas: 10
  targetCPUUtilizationPercentage: 60
```

### 7.3. Использование Helm

```bash
# Установить chart
helm install flight-delay-api ./flight-delay-api

# Обновить
helm upgrade flight-delay-api ./flight-delay-api

# Удалить
helm uninstall flight-delay-api
```

---

## Дополнительные ресурсы

- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [Minikube Handbook](https://minikube.sigs.k8s.io/)
- [Prometheus for Kubernetes](https://prometheus.io/docs/prometheus/latest/configuration/configuration/)
- [HorizontalPodAutoscaler](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/)

---

**✅ Лабораторная 10 завершена!** Микросервис успешно развёрнут в Kubernetes с автоматическим масштабированием.
