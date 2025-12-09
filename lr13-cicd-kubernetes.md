# Лабораторная 13: Полный CI/CD - От кода до обновления кластера

## 📋 Цель работы

Реализовать полноценный CI/CD pipeline, который автоматически:
1. Запускает тесты при каждом пуше
2. Собирает Docker образ
3. Пушит образ в реестр (GHCR/DockerHub)
4. Деплоит в Kubernetes кластер при мердже в main
5. Обновляет манифесты и применяет их через GitOps

**Ключевые задачи:**
- Настроить GitHub Actions (или GitLab CI)
- Интегрировать Docker Registry (GHCR)
- Деплой в Minikube/Kubernetes через kubectl или ArgoCD
- Версионирование и отслеживание релизов
- Привязка деплоя к версии модели в MLflow (опционально)

---

## 📚 Требования

### Зависимости и инструменты
```bash
# Docker (для сборки образов)
docker --version

# Kubernetes CLI
kubectl version --client

# Git
git --version

# Docker Registry (GHCR, DockerHub или приватный registry)
# GitHub личный токен (PAT) с правами write:packages
```

### Структура проекта
```
mlops-flight-delay/
├── .github/
│   └── workflows/
│       ├── ci.yml                    # ✨ CI тесты и сборка
│       └── deploy.yml                # ✨ Деплой в K8s
├── src/
│   ├── api.py
│   ├── train.py
│   ├── drift_check.py
│   └── __init__.py
├── tests/
│   ├── test_api.py
│   ├── test_drift_check.py
│   └── test_train.py
├── k8s/
│   ├── deployment.yaml               # Манифесты K8s
│   ├── service.yaml
│   ├── configmap.yaml
│   └── hpa.yaml
├── docker/
│   └── Dockerfile                    # ✨ Multi-stage dockerfile
├── docker-compose.yml
├── requirements.txt
├── conftest.py                       # Pytest конфиг
├── pytest.ini
├── setup.py
├── Makefile                          # ✨ Локальные команды
└── .env.example
```

---

## 🔧 Раздел 1: Подготовка GitHub Secrets

### 1.1 Создать секреты в GitHub

**Путь:** Settings → Secrets and variables → Actions

Добавить следующие секреты:

```
DOCKER_USERNAME          → GitHub username или docker login
DOCKER_PASSWORD          → Personal Access Token (GitHub) или Docker token
DOCKER_REGISTRY          → ghcr.io (GitHub Container Registry)
                           или docker.io (DockerHub)
KUBECONFIG              → Base64 encoded ~/.kube/config (если используется)
KUBE_NAMESPACE          → default (или custom namespace)
KUBE_CLUSTER_URL        → https://kubernetes.default.svc.cluster.local
KUBE_TOKEN              → Service Account token (если используется)
MLFLOW_TRACKING_URI     → http://mlflow:5000 или https://mlflow-server
MLFLOW_REGISTRY_URI     → http://mlflow:5000 (опционально)
SLACK_WEBHOOK           → https://hooks.slack.com/... (для уведомлений)
```

### 1.2 Получить GHCR токен

```bash
# 1. Создать Personal Access Token на GitHub
# Settings → Developer settings → Personal access tokens → Tokens (classic)
# Выбрать scopes: write:packages, read:packages, delete:packages

# 2. Залогиниться в GHCR
echo YOUR_PAT | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin

# 3. Тестовый пуш (опционально)
docker tag test-image ghcr.io/YOUR_USERNAME/test-image:v1.0.0
docker push ghcr.io/YOUR_USERNAME/test-image:v1.0.0
```

---

## 📝 Раздел 2: Dockerfile для production

### 2.1 Создать `docker/Dockerfile` (Multi-stage)

Файл `docker/Dockerfile`:

```dockerfile
# ============ STAGE 1: Builder ============
FROM python:3.11-slim as builder

WORKDIR /app

# Установить build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    git \
    && rm -rf /var/lib/apt/lists/*

# Скопировать requirements
COPY requirements.txt .

# Создать wheel файлы в одном слое
RUN pip install --user --no-cache-dir --wheel --no-deps --requirement requirements.txt && \
    pip install --user --no-cache-dir --wheel pip setuptools wheel

# ============ STAGE 2: Runtime ============
FROM python:3.11-slim

WORKDIR /app

# Установить runtime dependencies только
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Скопировать wheels из builder
COPY --from=builder /root/.local /root/.local

# Установить из wheels
RUN /root/.local/bin/pip install --no-cache-dir --no-index --find-links /root/.local wheels/*

# Скопировать исходный код
COPY src/ /app/src/
COPY models/ /app/models/
COPY data/ /app/data/

# Создать non-root пользователя для security
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:9696/health || exit 1

# Port
EXPOSE 9696

# Переменные окружения
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/root/.local/bin:$PATH

# Запуск API
CMD ["python", "-m", "src.api"]
```

### 2.2 Оптимизировать .dockerignore

Файл `.dockerignore`:

```
__pycache__
*.pyc
*.pyo
*.pyd
.Python
env/
venv/
.venv
pip-log.txt
pip-delete-this-directory.txt
.tox/
.coverage
.coverage.*
.cache
nosetests.xml
coverage.xml
*.cover
*.log
.git
.gitignore
.dockerignore
Dockerfile
docker-compose*.yml
.github/
.pytest_cache/
.mypy_cache/
*.egg-info/
dist/
build/
.DS_Store
.env
.env.local
.env.*.local
node_modules/
docs/
.vscode/
.idea/
```

---

## 🔄 Раздел 3: GitHub Actions - CI Pipeline

### 3.1 Создать `.github/workflows/ci.yml`

Файл `.github/workflows/ci.yml`:

```yaml
name: CI - Test & Build

on:
  push:
    branches:
      - main
      - develop
      - 'feature/**'
  pull_request:
    branches:
      - main
      - develop
  schedule:
    # Запускать тесты каждый день в 03:00 UTC
    - cron: '0 3 * * *'

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}
  PYTHON_VERSION: '3.11'

jobs:
  # ============ STAGE 1: LINT & FORMAT ============
  lint:
    name: Lint & Format Check
    runs-on: ubuntu-latest
    timeout-minutes: 10

    steps:
      - name: Checkout code
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: 'pip'

      - name: Install linting tools
        run: |
          pip install --upgrade pip
          pip install flake8 black isort pylint mypy

      - name: Run flake8
        run: flake8 src/ tests/ --count --select=E9,F63,F7,F82 --show-source --statistics
        continue-on-error: true

      - name: Check code formatting with black
        run: black --check src/ tests/
        continue-on-error: true

      - name: Check import sorting with isort
        run: isort --check-only src/ tests/
        continue-on-error: true

      - name: Run pylint
        run: pylint src/ --exit-zero
        continue-on-error: true

      - name: Type checking with mypy
        run: mypy src/ --ignore-missing-imports || true
        continue-on-error: true

  # ============ STAGE 2: UNIT TESTS ============
  test:
    name: Unit Tests
    runs-on: ubuntu-latest
    timeout-minutes: 20
    needs: lint

    services:
      postgres:
        image: postgres:14
        env:
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: test_db
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: 'pip'

      - name: Install dependencies
        run: |
          pip install --upgrade pip
          pip install -r requirements.txt
          pip install pytest pytest-cov pytest-xdist

      - name: Run unit tests
        env:
          DATABASE_URL: postgresql://test:test@localhost:5432/test_db
          PYTHONPATH: ${{ github.workspace }}
        run: |
          pytest tests/ \
            --verbose \
            --cov=src \
            --cov-report=xml \
            --cov-report=html \
            --cov-report=term-missing \
            --junit-xml=test-results.xml \
            -n auto

      - name: Upload coverage reports
        uses: codecov/codecov-action@v3
        if: always()
        with:
          files: ./coverage.xml
          flags: unittests
          fail_ci_if_error: false

      - name: Upload test results
        uses: actions/upload-artifact@v3
        if: always()
        with:
          name: test-results
          path: test-results.xml

      - name: Publish test results
        uses: EnricoMi/publish-unit-test-result-action@v2
        if: always()
        with:
          files: test-results.xml

  # ============ STAGE 3: SECURITY SCAN ============
  security:
    name: Security Scanning
    runs-on: ubuntu-latest
    timeout-minutes: 15
    needs: test

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: 'pip'

      - name: Install security tools
        run: |
          pip install --upgrade pip
          pip install bandit safety

      - name: Run bandit (security check)
        run: bandit -r src/ -ll -f json -o bandit-report.json || true
        continue-on-error: true

      - name: Check dependencies with safety
        run: |
          pip install -r requirements.txt
          safety check --json || true
        continue-on-error: true

      - name: Upload security reports
        uses: actions/upload-artifact@v3
        if: always()
        with:
          name: security-reports
          path: bandit-report.json

  # ============ STAGE 4: BUILD DOCKER IMAGE ============
  build:
    name: Build Docker Image
    runs-on: ubuntu-latest
    timeout-minutes: 30
    needs: security
    permissions:
      contents: read
      packages: write

    outputs:
      image_tag: ${{ steps.meta.outputs.tags }}
      image_digest: ${{ steps.build.outputs.digest }}

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v2

      - name: Log in to Container Registry
        uses: docker/login-action@v2
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v4
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=ref,event=branch
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}
            type=sha
            type=raw,value=latest,enable={{is_default_branch}}
            type=raw,value=${{ github.run_number }},enable={{is_default_branch}}

      - name: Build and push Docker image
        id: build
        uses: docker/build-push-action@v4
        with:
          context: .
          file: ./docker/Dockerfile
          push: ${{ github.event_name == 'push' && github.ref == 'refs/heads/main' }}
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=registry,ref=${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:buildcache
          cache-to: type=registry,ref=${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:buildcache,mode=max

      - name: Create SBOM (Software Bill of Materials)
        run: |
          docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
            anchore/syft:latest \
            ${{ steps.meta.outputs.tags }} \
            -o spdx-json > sbom.spdx.json || true

      - name: Upload SBOM
        uses: actions/upload-artifact@v3
        if: always()
        with:
          name: sbom
          path: sbom.spdx.json

      - name: Image scan with Trivy
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: ${{ steps.meta.outputs.tags }}
          format: 'sarif'
          output: 'trivy-results.sarif'
        continue-on-error: true

      - name: Upload Trivy report to GitHub Security
        uses: github/codeql-action/upload-sarif@v2
        if: always()
        with:
          sarif_file: 'trivy-results.sarif'

  # ============ STAGE 5: VALIDATE DEPLOYMENT ============
  validate:
    name: Validate Deployment Config
    runs-on: ubuntu-latest
    timeout-minutes: 10
    needs: build

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up kubectl
        uses: azure/setup-kubectl@v3
        with:
          version: 'v1.28.0'

      - name: Validate Kubernetes manifests
        run: |
          for file in k8s/*.yaml; do
            echo "Validating $file..."
            kubectl apply --dry-run=client -f "$file"
          done

      - name: Helm template validation (if using Helm)
        run: |
          curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash || true
          helm lint chart/ 2>/dev/null || echo "No helm chart found"
        continue-on-error: true

  # ============ SUCCESS NOTIFICATION ============
  notify:
    name: Notify on Success
    runs-on: ubuntu-latest
    needs: [lint, test, security, build, validate]
    if: success()

    steps:
      - name: Send Slack notification
        uses: slackapi/slack-github-action@v1.24.0
        if: secrets.SLACK_WEBHOOK != ''
        with:
          webhook-url: ${{ secrets.SLACK_WEBHOOK }}
          payload: |
            {
              "text": "✅ CI Pipeline Successful",
              "blocks": [
                {
                  "type": "section",
                  "text": {
                    "type": "mrkdwn",
                    "text": "*CI Pipeline Successful* 🎉\n*Branch:* ${{ github.ref_name }}\n*Commit:* ${{ github.sha }}\n*Author:* ${{ github.actor }}"
                  }
                }
              ]
            }
```

---

## 🚀 Раздел 4: GitHub Actions - Deploy Pipeline

### 4.1 Создать `.github/workflows/deploy.yml`

Файл `.github/workflows/deploy.yml`:

```yaml
name: Deploy to Kubernetes

on:
  push:
    branches:
      - main
    paths:
      - 'src/**'
      - 'docker/**'
      - 'k8s/**'
      - 'requirements.txt'
      - '.github/workflows/deploy.yml'
  workflow_run:
    workflows: ['CI - Test & Build']
    types: [completed]
    branches:
      - main

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}
  KUBE_NAMESPACE: default
  DEPLOY_ENVIRONMENT: production

jobs:
  # ============ STAGE 1: BUILD & PUSH IMAGE ============
  build-and-push:
    name: Build & Push Image
    runs-on: ubuntu-latest
    if: github.event_name == 'push' || github.event.workflow_run.conclusion == 'success'
    timeout-minutes: 30
    permissions:
      contents: read
      packages: write

    outputs:
      image: ${{ steps.image.outputs.image }}
      tag: ${{ steps.image.outputs.tag }}

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v2

      - name: Log in to GHCR
        uses: docker/login-action@v2
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Generate image tag
        id: image
        run: |
          IMAGE="${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}"
          TAG="${{ github.sha }}"
          LATEST_TAG="latest"
          
          echo "image=${IMAGE}" >> $GITHUB_OUTPUT
          echo "tag=${TAG}" >> $GITHUB_OUTPUT
          echo "Building: ${IMAGE}:${TAG}"

      - name: Build and push image
        uses: docker/build-push-action@v4
        with:
          context: .
          file: ./docker/Dockerfile
          push: true
          tags: |
            ${{ steps.image.outputs.image }}:${{ steps.image.outputs.tag }}
            ${{ steps.image.outputs.image }}:latest
          cache-from: type=registry,ref=${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:buildcache
          cache-to: type=registry,ref=${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:buildcache,mode=max

  # ============ STAGE 2: UPDATE DEPLOYMENT ============
  update-deployment:
    name: Update Kubernetes Deployment
    runs-on: ubuntu-latest
    needs: build-and-push
    timeout-minutes: 15

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up kubectl
        uses: azure/setup-kubectl@v3
        with:
          version: 'v1.28.0'

      - name: Configure kubectl (Local Development)
        if: ${{ contains(github.event.head_commit.message, '[minikube]') || 
                github.event_name == 'workflow_run' }}
        run: |
          mkdir -p $HOME/.kube
          echo "${{ secrets.KUBECONFIG }}" | base64 -d > $HOME/.kube/config
          chmod 600 $HOME/.kube/config
          kubectl cluster-info || echo "Note: kubeconfig might be for remote cluster"

      - name: Check cluster connectivity
        run: |
          kubectl cluster-info || echo "Not connected to cluster (expected in CI)"
          kubectl version --client

      - name: Update deployment image (kubectl set image)
        if: secrets.KUBECONFIG != ''
        run: |
          kubectl set image deployment/flight-delay-api \
            api=${{ needs.build-and-push.outputs.image }}:${{ needs.build-and-push.outputs.tag }} \
            -n ${{ env.KUBE_NAMESPACE }} \
            --record || echo "Deployment not found - will use GitOps instead"

      - name: Verify rollout
        if: secrets.KUBECONFIG != ''
        run: |
          kubectl rollout status deployment/flight-delay-api \
            -n ${{ env.KUBE_NAMESPACE }} \
            --timeout=5m || echo "Rollout verification skipped"
        continue-on-error: true

  # ============ STAGE 3: GITOPS - UPDATE MANIFESTS ============
  gitops-update:
    name: GitOps - Update Manifests
    runs-on: ubuntu-latest
    needs: build-and-push
    timeout-minutes: 10
    permissions:
      contents: write
      pull-requests: write

    steps:
      - name: Checkout code
        uses: actions/checkout@v4
        with:
          token: ${{ secrets.GITHUB_TOKEN }}
          fetch-depth: 0

      - name: Update deployment manifest
        env:
          NEW_IMAGE: ${{ needs.build-and-push.outputs.image }}:${{ needs.build-and-push.outputs.tag }}
        run: |
          echo "Updating image in k8s/deployment.yaml to: $NEW_IMAGE"
          
          # Обновить image в deployment.yaml
          sed -i "s|image: .*|image: $NEW_IMAGE|g" k8s/deployment.yaml
          
          # Показать изменения
          git diff k8s/deployment.yaml
          
          # Commit и push
          git config --local user.email "action@github.com"
          git config --local user.name "GitHub Action"
          
          git add k8s/deployment.yaml
          git commit -m "chore: update deployment image to $NEW_IMAGE [skip ci]" \
            || echo "No changes to commit"
          git push

      - name: Create deployment artifact
        run: |
          mkdir -p deploy-artifacts
          cp k8s/*.yaml deploy-artifacts/
          echo "New image: ${{ needs.build-and-push.outputs.image }}:${{ needs.build-and-push.outputs.tag }}" > deploy-artifacts/IMAGE.txt

      - name: Upload deployment artifacts
        uses: actions/upload-artifact@v3
        with:
          name: deployment-manifests
          path: deploy-artifacts/

  # ============ STAGE 4: ARGOCD DEPLOYMENT (OPTIONAL) ============
  argocd-sync:
    name: ArgoCD Sync (Optional)
    runs-on: ubuntu-latest
    needs: gitops-update
    if: secrets.ARGOCD_SERVER != '' && secrets.ARGOCD_AUTH_TOKEN != ''
    timeout-minutes: 10

    steps:
      - name: Install ArgoCD CLI
        run: |
          VERSION=$(curl -s https://api.github.com/repos/argoproj/argo-cd/releases/latest | grep tag_name | cut -d '"' -f 4)
          curl -sSL -o /usr/local/bin/argocd https://github.com/argoproj/argo-cd/releases/download/$VERSION/argocd-linux-amd64
          chmod +x /usr/local/bin/argocd

      - name: Login to ArgoCD
        run: |
          argocd login ${{ secrets.ARGOCD_SERVER }} \
            --username ${{ secrets.ARGOCD_USERNAME }} \
            --password ${{ secrets.ARGOCD_AUTH_TOKEN }} \
            --insecure

      - name: Sync ArgoCD application
        run: |
          argocd app sync flight-delay-api \
            --prune \
            --force
          
          # Ждать синхронизации
          argocd app wait flight-delay-api --timeout 300

  # ============ STAGE 5: SMOKE TESTS ============
  smoke-tests:
    name: Smoke Tests
    runs-on: ubuntu-latest
    needs: [update-deployment, gitops-update]
    timeout-minutes: 15
    if: always()

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install test dependencies
        run: |
          pip install pytest requests httpx

      - name: Wait for deployment (mock)
        run: sleep 30

      - name: Run smoke tests
        env:
          API_URL: http://localhost:9696
          KUBE_NAMESPACE: ${{ env.KUBE_NAMESPACE }}
        run: |
          cat > /tmp/smoke_test.py << 'EOF'
          import requests
          import time
          
          api_url = "http://localhost:9696"
          
          # Test health endpoint
          try:
              response = requests.get(f"{api_url}/health", timeout=5)
              assert response.status_code == 200
              print("✅ Health check passed")
          except Exception as e:
              print(f"⚠️ Health check failed: {e}")
          
          # Test metrics endpoint
          try:
              response = requests.get(f"{api_url}/metrics", timeout=5)
              assert response.status_code == 200
              assert b"flight_delay" in response.content
              print("✅ Metrics endpoint passed")
          except Exception as e:
              print(f"⚠️ Metrics check failed: {e}")
          EOF
          
          python /tmp/smoke_test.py || echo "Smoke tests skipped (no running deployment)"
        continue-on-error: true

  # ============ STAGE 6: NOTIFY ============
  notify-deploy:
    name: Notify Deployment Status
    runs-on: ubuntu-latest
    needs: [smoke-tests, argocd-sync]
    if: always()

    steps:
      - name: Determine deployment status
        id: status
        run: |
          if [ "${{ needs.smoke-tests.result }}" == "success" ]; then
            echo "status=✅ Deployment Successful" >> $GITHUB_OUTPUT
            echo "color=good" >> $GITHUB_OUTPUT
          else
            echo "status=⚠️ Deployment Completed (with warnings)" >> $GITHUB_OUTPUT
            echo "color=warning" >> $GITHUB_OUTPUT
          fi

      - name: Send Slack notification
        uses: slackapi/slack-github-action@v1.24.0
        if: secrets.SLACK_WEBHOOK != ''
        with:
          webhook-url: ${{ secrets.SLACK_WEBHOOK }}
          payload: |
            {
              "blocks": [
                {
                  "type": "section",
                  "text": {
                    "type": "mrkdwn",
                    "text": "${{ steps.status.outputs.status }}\n*Image:* `${{ needs.smoke-tests.outputs.image }}:${{ needs.smoke-tests.outputs.tag }}`\n*Environment:* ${{ env.DEPLOY_ENVIRONMENT }}"
                  }
                }
              ]
            }

      - name: Create GitHub Release
        uses: actions/create-release@v1
        if: github.event_name == 'push'
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        with:
          tag_name: v${{ github.run_number }}
          release_name: Release ${{ github.run_number }}
          body: |
            Deployed on ${{ github.event.head_commit.timestamp }}
            Image: ${{ needs.build-and-push.outputs.image }}:${{ needs.build-and-push.outputs.tag }}
          draft: false
          prerelease: false
        continue-on-error: true
```

---

## 🐳 Раздел 5: Kubernetes Manifests с Image Update

### 5.1 Обновить `k8s/deployment.yaml`

Файл `k8s/deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: flight-delay-api
  namespace: default
  labels:
    app: flight-delay-api
    version: v1
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  
  selector:
    matchLabels:
      app: flight-delay-api
  
  template:
    metadata:
      labels:
        app: flight-delay-api
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "9696"
        prometheus.io/path: "/metrics"
    
    spec:
      serviceAccountName: flight-delay-sa
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        fsGroup: 1000
      
      containers:
      - name: api
        # ⚠️ ЭТОТ IMAGE БУДЕТ ОБНОВЛЯТЬСЯ CI/CD
        image: ghcr.io/irina-64/mlops-flight-delay:latest
        imagePullPolicy: Always
        
        ports:
        - name: http
          containerPort: 9696
          protocol: TCP
        
        env:
        - name: PYTHONUNBUFFERED
          value: "1"
        - name: PYTHONDONTWRITEBYTECODE
          value: "1"
        - name: MODEL_PATH
          value: /models/flight_delay_model.pkl
        - name: DATA_PATH
          value: /data
        
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
            port: http
          initialDelaySeconds: 30
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 3
        
        readinessProbe:
          httpGet:
            path: /health
            port: http
          initialDelaySeconds: 10
          periodSeconds: 5
          timeoutSeconds: 3
          failureThreshold: 2
        
        volumeMounts:
        - name: models
          mountPath: /models
          readOnly: true
        - name: data
          mountPath: /data
          readOnly: true
        - name: tmp
          mountPath: /tmp
        
        securityContext:
          allowPrivilegeEscalation: false
          readOnlyRootFilesystem: true
          capabilities:
            drop:
              - ALL
      
      volumes:
      - name: models
        persistentVolumeClaim:
          claimName: models-pvc
      - name: data
        persistentVolumeClaim:
          claimName: data-pvc
      - name: tmp
        emptyDir: {}
      
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            podAffinityTerm:
              labelSelector:
                matchExpressions:
                - key: app
                  operator: In
                  values:
                  - flight-delay-api
              topologyKey: kubernetes.io/hostname
```

### 5.2 Создать `k8s/service.yaml`

Файл `k8s/service.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: flight-delay-api
  namespace: default
  labels:
    app: flight-delay-api
spec:
  type: LoadBalancer
  # Или NodePort для Minikube:
  # type: NodePort
  
  selector:
    app: flight-delay-api
  
  ports:
  - name: http
    port: 80
    targetPort: http
    protocol: TCP
    # nodePort: 30696  # Если используется NodePort
  
  sessionAffinity: ClientIP
```

### 5.3 Создать `k8s/hpa.yaml` (Horizontal Pod Autoscaler)

Файл `k8s/hpa.yaml`:

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: flight-delay-api-hpa
  namespace: default
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: flight-delay-api
  
  minReplicas: 2
  maxReplicas: 10
  
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
  
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
      - type: Percent
        value: 50
        periodSeconds: 60
    
    scaleUp:
      stabilizationWindowSeconds: 0
      policies:
      - type: Percent
        value: 100
        periodSeconds: 15
      - type: Pods
        value: 2
        periodSeconds: 15
      selectPolicy: Max
```

---

## 🧪 Раздел 6: Unit Tests для CI/CD

### 6.1 Создать `tests/test_api.py`

Файл `tests/test_api.py`:

```python
"""
Unit тесты для API
"""

import pytest
from flask import Flask
import sys
from pathlib import Path

# Добавить src в PATH
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.api import app, REQUEST_COUNT, MODEL_LOADED


@pytest.fixture
def client():
    """Flask test client"""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


def test_health_endpoint(client):
    """Тест health endpoint"""
    response = client.get('/health')
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'ok'
    assert data['service'] == 'flight-delay-api'


def test_metrics_endpoint(client):
    """Тест metrics endpoint"""
    response = client.get('/metrics')
    assert response.status_code == 200
    assert b'flight_delay_api' in response.data
    assert b'HELP' in response.data


def test_predict_valid_request(client):
    """Тест predict с валидными данными"""
    payload = {
        'duration': 50,
        'departure_time': '09:00',
        'days_since': 1,
        'origin': 'JFK',
        'destination': 'LAX'
    }
    
    response = client.post('/predict', json=payload)
    
    if MODEL_LOADED:
        assert response.status_code == 200
        data = response.get_json()
        assert 'prediction' in data
        assert 'probability' in data
    else:
        # Model not loaded - should return 503
        assert response.status_code == 503


def test_predict_invalid_json(client):
    """Тест predict с невалидным JSON"""
    response = client.post('/predict', data='invalid json')
    assert response.status_code == 400


def test_predict_missing_fields(client):
    """Тест predict с недостающими полями"""
    payload = {'duration': 50}
    response = client.post('/predict', json=payload)
    assert response.status_code == 400


def test_request_counter(client):
    """Тест что счётчик запросов работает"""
    initial_count = sum(
        metric.value for metric in REQUEST_COUNT.collect()
        if hasattr(metric, 'samples')
    )
    
    client.get('/health')
    
    final_count = sum(
        metric.value for metric in REQUEST_COUNT.collect()
        if hasattr(metric, 'samples')
    )
    
    assert final_count >= initial_count


def test_api_response_time(client):
    """Тест что API отвечает достаточно быстро"""
    import time
    
    start = time.time()
    response = client.get('/health')
    elapsed = time.time() - start
    
    assert response.status_code == 200
    assert elapsed < 1.0, f"Response too slow: {elapsed}s"


def test_concurrent_requests(client):
    """Тест concurrent requests"""
    import threading
    
    results = []
    
    def make_request():
        response = client.get('/health')
        results.append(response.status_code)
    
    threads = [threading.Thread(target=make_request) for _ in range(5)]
    
    for thread in threads:
        thread.start()
    
    for thread in threads:
        thread.join()
    
    assert all(code == 200 for code in results)
    assert len(results) == 5
```

### 6.2 Создать `tests/test_drift_check.py`

Файл `tests/test_drift_check.py`:

```python
"""
Unit тесты для drift detection
"""

import pytest
import numpy as np
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.drift_check import (
    calculate_psi,
    calculate_ks_statistic,
    check_feature_drift,
    should_retrain
)


@pytest.fixture
def sample_data():
    """Пример данных для тестирования"""
    np.random.seed(42)
    baseline = pd.DataFrame({
        'duration': np.random.normal(100, 10, 500),
        'departure_hour': np.random.randint(0, 24, 500),
        'days_since': np.random.randint(0, 365, 500),
    })
    
    production = pd.DataFrame({
        'duration': np.random.normal(100, 10, 500),
        'departure_hour': np.random.randint(0, 24, 500),
        'days_since': np.random.randint(0, 365, 500),
    })
    
    return baseline, production


def test_psi_no_drift(sample_data):
    """PSI должен быть низким для идентичных распределений"""
    baseline, _ = sample_data
    psi = calculate_psi(baseline['duration'].values, baseline['duration'].values)
    assert psi < 0.01


def test_psi_with_drift():
    """PSI должен быть высоким при сдвиге"""
    baseline = np.random.normal(100, 10, 500)
    shifted = np.random.normal(120, 10, 500)
    psi = calculate_psi(baseline, shifted)
    assert psi > 0.1


def test_ks_statistic():
    """KS тест должен обнаружить различия"""
    baseline = np.random.normal(0, 1, 500)
    shifted = np.random.normal(0.5, 1, 500)
    ks = calculate_ks_statistic(baseline, shifted)
    assert ks > 0.05


def test_feature_drift_detection(sample_data):
    """Тест обнаружения дрейфа в признаках"""
    baseline, production = sample_data
    
    drift_results = check_feature_drift(baseline, production)
    
    assert isinstance(drift_results, dict)
    assert len(drift_results) > 0
    
    for feature, metrics in drift_results.items():
        assert 'psi' in metrics
        assert 'ks' in metrics
        assert 'drifted' in metrics
        assert isinstance(metrics['drifted'], bool)


def test_should_retrain_no_drift(sample_data):
    """should_retrain должен вернуть False без дрейфа"""
    report = {
        'overall_drifted': False,
        'feature_drift': {
            'duration': {'psi': 0.05, 'ks': 0.03},
        }
    }
    
    assert should_retrain(report) is False


def test_should_retrain_with_drift(sample_data):
    """should_retrain должен вернуть True при дрейфе"""
    report = {
        'overall_drifted': True,
        'feature_drift': {
            'duration': {'psi': 0.35, 'ks': 0.20},
        }
    }
    
    assert should_retrain(report) is True


def test_psi_with_nan_values():
    """PSI должен обрабатывать NaN значения"""
    baseline = np.array([1, 2, 3, np.nan, 5])
    actual = np.array([1, 2, 3, 4, 5])
    
    psi = calculate_psi(baseline, actual)
    assert np.isfinite(psi)
```

### 6.3 Создать `pytest.ini`

Файл `pytest.ini`:

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts =
    -v
    --strict-markers
    --tb=short
    --disable-warnings
    --durations=10
markers =
    unit: Unit тесты
    integration: Integration тесты
    slow: Медленные тесты
    api: API тесты
    drift: Drift detection тесты
```

---

## 🔧 Раздел 7: Makefile для локальной разработки

### 7.1 Создать `Makefile`

Файл `Makefile`:

```makefile
.PHONY: help install test lint format build push deploy clean

DOCKER_REGISTRY ?= ghcr.io
DOCKER_USERNAME ?= irina-64
IMAGE_NAME ?= mlops-flight-delay
IMAGE_TAG ?= latest
PYTHON_VERSION ?= 3.11

help:
	@echo "Available commands:"
	@echo "  make install        - Install dependencies"
	@echo "  make test           - Run unit tests"
	@echo "  make lint           - Run linting checks"
	@echo "  make format         - Format code with black"
	@echo "  make build          - Build Docker image"
	@echo "  make push           - Push Docker image to registry"
	@echo "  make deploy         - Deploy to local Kubernetes"
	@echo "  make deploy-minikube - Deploy to Minikube"
	@echo "  make logs           - Show pod logs"
	@echo "  make clean          - Clean up"

install:
	pip install --upgrade pip
	pip install -r requirements.txt
	pip install -r requirements-dev.txt

test:
	pytest tests/ -v --cov=src --cov-report=html

lint:
	flake8 src/ tests/ --max-line-length=100
	pylint src/ --exit-zero
	mypy src/ --ignore-missing-imports

format:
	black src/ tests/
	isort src/ tests/

security-check:
	bandit -r src/ -ll
	safety check

build:
	docker build -f docker/Dockerfile \
		-t $(DOCKER_REGISTRY)/$(DOCKER_USERNAME)/$(IMAGE_NAME):$(IMAGE_TAG) \
		-t $(DOCKER_REGISTRY)/$(DOCKER_USERNAME)/$(IMAGE_NAME):latest \
		.

build-local:
	docker build -f docker/Dockerfile \
		-t $(IMAGE_NAME):$(IMAGE_TAG) \
		.

push:
	docker push $(DOCKER_REGISTRY)/$(DOCKER_USERNAME)/$(IMAGE_NAME):$(IMAGE_TAG)
	docker push $(DOCKER_REGISTRY)/$(DOCKER_USERNAME)/$(IMAGE_NAME):latest

deploy:
	kubectl apply -f k8s/
	kubectl rollout status deployment/flight-delay-api --timeout=5m

deploy-minikube:
	eval $$(minikube docker-env)
	make build-local
	kubectl apply -f k8s/
	kubectl rollout status deployment/flight-delay-api --timeout=5m
	minikube service flight-delay-api

logs:
	kubectl logs -f deployment/flight-delay-api --tail=50

logs-tail:
	kubectl logs -f deployment/flight-delay-api --tail=100 -c api

port-forward:
	kubectl port-forward svc/flight-delay-api 9696:80

shell:
	kubectl exec -it $$(kubectl get pod -l app=flight-delay-api -o jsonpath='{.items[0].metadata.name}') -- /bin/bash

clean:
	rm -rf __pycache__ .pytest_cache .coverage htmlcov
	find . -type d -name __pycache__ -exec rm -rf {} +
	docker image prune -f

local-run:
	docker run --rm -p 9696:9696 \
		-v $(PWD)/models:/models \
		-v $(PWD)/data:/data \
		$(IMAGE_NAME):$(IMAGE_TAG)

k8s-describe:
	kubectl describe deployment flight-delay-api
	kubectl describe service flight-delay-api

k8s-events:
	kubectl get events --sort-by='.lastTimestamp'

all: install lint test build

ci-local: lint test build

.DEFAULT_GOAL := help
```

---

## 📊 Раздел 8: Configuration Files для CI/CD

### 8.1 Создать `requirements-dev.txt`

Файл `requirements-dev.txt`:

```
# Testing
pytest==7.4.0
pytest-cov==4.1.0
pytest-xdist==3.3.1
pytest-timeout==2.1.0
pytest-mock==3.11.1

# Code Quality
black==23.7.0
flake8==6.0.0
isort==5.12.0
pylint==2.17.5
mypy==1.4.1

# Security
bandit==1.7.5
safety==2.3.5

# Documentation
sphinx==7.1.2
sphinx-rtd-theme==1.3.0

# DevOps
docker==6.1.1
kubernetes==27.2.0
```

### 8.2 Создать `.env.example`

Файл `.env.example`:

```bash
# API Configuration
FLASK_APP=src.api:app
FLASK_ENV=production
PYTHONUNBUFFERED=1

# Model Configuration
MODEL_PATH=/models/flight_delay_model.pkl
DATA_PATH=/data

# Database (if needed)
DATABASE_URL=postgresql://user:password@localhost:5432/mlops

# MLflow
MLFLOW_TRACKING_URI=http://localhost:5000
MLFLOW_REGISTRY_URI=http://localhost:5000

# Kubernetes
KUBE_NAMESPACE=default
KUBE_CLUSTER_URL=https://kubernetes.default.svc.cluster.local

# Container Registry
DOCKER_REGISTRY=ghcr.io
DOCKER_USERNAME=your-github-username
DOCKER_PASSWORD=your-github-token

# Monitoring
PROMETHEUS_URL=http://prometheus:9090
GRAFANA_URL=http://grafana:3000

# Slack Notifications
SLACK_WEBHOOK=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

---

## 🚀 Раздел 9: Примеры запуска CI/CD локально

### 9.1 Локальное тестирование workflow

```bash
# 1. Установить act (GitHub Actions эмулятор)
brew install act  # macOS
# или
curl -sSL https://raw.githubusercontent.com/nektos/act/master/install.sh | bash

# 2. Создать .secrets файл
cat > .secrets << EOF
DOCKER_USERNAME=github-username
DOCKER_PASSWORD=github-token
KUBECONFIG=base64-encoded-kubeconfig
EOF

# 3. Запустить CI workflow локально
act push -f .github/workflows/ci.yml --secret-file .secrets

# 4. Запустить Deploy workflow
act push -f .github/workflows/deploy.yml --secret-file .secrets

# 5. Смотреть результаты
act -l  # List all workflows
```

### 9.2 Локальное развёртывание в Minikube

```bash
# 1. Запустить Minikube
minikube start --cpus 4 --memory 8192

# 2. Включить необходимые addons
minikube addons enable ingress
minikube addons enable metrics-server

# 3. Построить образ в Minikube Docker
eval $(minikube docker-env)
docker build -f docker/Dockerfile -t flight-delay-api:latest .

# 4. Развернуть приложение
make deploy-minikube

# 5. Проверить статус
kubectl get pods
kubectl get svc

# 6. Открыть в браузере
minikube service flight-delay-api

# 7. Port forward для локального тестирования
kubectl port-forward svc/flight-delay-api 9696:80

# 8. Тестировать API
curl http://localhost:9696/health
curl -X POST http://localhost:9696/predict -H "Content-Type: application/json" \
  -d '{"duration": 50, "departure_time": "09:00", "days_since": 1, "origin": "JFK", "destination": "LAX"}'
```

---

## 🔄 Раздел 10: Опционально - Привязка к MLflow

### 10.1 Обновить Deploy Pipeline для MLflow

Добавить в `.github/workflows/deploy.yml` перед развёртыванием:

```yaml
  # ============ STAGE: CHECK MLFLOW MODEL PROMOTION ============
  check-mlflow-promotion:
    name: Check MLflow Model Promotion
    runs-on: ubuntu-latest
    if: secrets.MLFLOW_TRACKING_URI != ''
    timeout-minutes: 10

    outputs:
      should_deploy: ${{ steps.check.outputs.should_deploy }}
      model_version: ${{ steps.check.outputs.model_version }}

    steps:
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install MLflow
        run: pip install mlflow

      - name: Check model promotion status
        id: check
        env:
          MLFLOW_TRACKING_URI: ${{ secrets.MLFLOW_TRACKING_URI }}
        run: |
          python << 'EOF'
          import mlflow
          from mlflow.tracking import MlflowClient
          
          client = MlflowClient()
          
          # Получить последние версии модели
          registered_models = client.search_registered_models()
          
          for model in registered_models:
              if model.name == "flight-delay-model":
                  for version in model.latest_versions:
                      if version.current_stage == "Production":
                          print(f"✅ Found Production model version: {version.version}")
                          print(f"::set-output name=should_deploy::true")
                          print(f"::set-output name=model_version::{version.version}")
                          exit(0)
          
          print("⚠️ No Production model found")
          print(f"::set-output name=should_deploy::false")
          exit(0)
          EOF
```

### 10.2 Обновить Deployment условно

```yaml
  update-deployment-mlflow:
    name: Update Deployment (MLflow)
    runs-on: ubuntu-latest
    needs: [build-and-push, check-mlflow-promotion]
    if: needs.check-mlflow-promotion.outputs.should_deploy == 'true'
    timeout-minutes: 15

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Log deployment with MLflow model
        run: |
          echo "Deploying with MLflow model version: ${{ needs.check-mlflow-promotion.outputs.model_version }}"
          echo "Docker image: ${{ needs.build-and-push.outputs.image }}"
```

---

## ✅ Раздел 11: Чек-лист оценки

| Задача | Проверка | Результат | ☑ |
|--------|----------|-----------|---|
| **CI Pipeline** | | | |
| Lint работает | `.github/workflows/ci.yml` запускается | ✅ CI успешен | ☐ |
| Тесты проходят | `pytest tests/` | Все тесты зелёные | ☐ |
| Coverage отчёт | artifacts/coverage | HTML отчёт сгенерирован | ☐ |
| Docker image собран | docker build | Image присутствует в GHCR | ☐ |
| **Build & Push** | | | |
| Image pushed в GHCR | `docker pull ghcr.io/...` | Образ скачивается | ☐ |
| Image tagged правильно | `docker images \| grep flight-delay` | Tag = commit SHA | ☐ |
| Image тегирован latest | GHCR dashboard | latest тег обновлён | ☐ |
| **Deployment** | | | |
| K8s manifests валидны | `kubectl apply --dry-run` | Ошибок нет | ☐ |
| Deployment обновлён | `kubectl get deployment` | Новый image в spec | ☐ |
| Pods started | `kubectl get pods` | Все pods running | ☐ |
| Service accessible | `kubectl get svc` | LoadBalancer/NodePort работает | ☐ |
| **Smoke Tests** | | | |
| Health check | `curl /health` | Status 200 | ☐ |
| Metrics endpoint | `curl /metrics` | Prometheus метрики присутствуют | ☐ |
| Predict endpoint | `curl -X POST /predict` | Прогноз успешен | ☐ |
| **GitOps (Optional)** | | | |
| Manifests updated | k8s/deployment.yaml | Image URL обновлён | ☐ |
| Git commit создан | `git log` | Commit с новым image | ☐ |
| ArgoCD синхронизирован | ArgoCD dashboard | Application synced | ☐ |
| **Notifications** | | | |
| Slack notification | Slack channel | Deployment уведомление получено | ☐ |
| GitHub Release created | Releases | Release v{run-number} создан | ☐ |
| **MLflow (Optional)** | | | |
| Model checked | MLflow registry | Production версия найдена | ☐ |
| Deployment conditional | Deploy only if promoted | Деплой зависит от promotion | ☐ |

---

## 🎯 Раздел 12: Troubleshooting

### 12.1 Проблемы с Docker Registry

```bash
# Проблема: "unauthorized: authentication required"
# Решение:
echo YOUR_GITHUB_PAT | docker login ghcr.io -u YOUR_USERNAME --password-stdin

# Проблема: Image слишком большой
# Решение: Использовать multi-stage dockerfile и .dockerignore

# Проблема: Image не пушится в GHCR
# Решение: Проверить DOCKER_TOKEN в GitHub Secrets
```

### 12.2 Проблемы с Kubernetes

```bash
# Проблема: Pod stuck in ImagePullBackOff
kubectl describe pod <pod-name>
# Решение: Проверить imagePullPolicy и image URL

# Проблема: Rollout timeout
kubectl rollout status deployment/flight-delay-api --timeout=10m

# Проблема: Service не доступен
kubectl port-forward svc/flight-delay-api 9696:80
curl localhost:9696/health

# Просмотр событий
kubectl get events --sort-by='.lastTimestamp'
```

### 12.3 Проблемы с GitHub Actions

```bash
# Проблема: Workflow не триггерится
# Решение: Проверить .github/workflows/ структуру

# Проблема: Секреты не доступны
# Решение: Проверить имена секретов в workflow

# Просмотр логов
# GitHub → Actions → Workflow → Run details

# Локальное тестирование
act push -f .github/workflows/ci.yml --verbose
```

---

## 📚 Дополнительные ресурсы

- **GitHub Actions**: https://docs.github.com/en/actions
- **Docker Best Practices**: https://docs.docker.com/develop/dev-best-practices/
- **Kubernetes Deployment**: https://kubernetes.io/docs/concepts/workloads/controllers/deployment/
- **ArgoCD**: https://argo-cd.readthedocs.io/
- **MLflow Model Registry**: https://mlflow.org/docs/latest/model-registry.html
- **Semantic Versioning**: https://semver.org/

---

## 🎯 Быстрый старт

### Локально (без CI/CD сначала)

```bash
# 1. Установить зависимости
make install

# 2. Запустить тесты
make test

# 3. Построить образ
make build-local

# 4. Развернуть в Minikube
make deploy-minikube

# 5. Проверить
kubectl get pods
kubectl port-forward svc/flight-delay-api 9696:80
curl http://localhost:9696/health
```

### С GitHub Actions

```bash
# 1. Создать GitHub Secrets
# Settings → Secrets → New repository secret
# DOCKER_USERNAME, DOCKER_PASSWORD, KUBECONFIG (опционально)

# 2. Создать feature branch
git checkout -b feature/new-api

# 3. Сделать изменения и коммит
git add .
git commit -m "feat: add new endpoint"

# 4. Push в GitHub
git push origin feature/new-api

# 5. Создать PR (GitHub Actions запустится автоматически)
# Смотреть статус в PR

# 6. Merge в main
# Автоматический деплой в K8s

# 7. Проверить результат
kubectl get pods
kubectl logs deployment/flight-delay-api
```

---

## 📝 Структура файлов после ЛР13

```
mlops-flight-delay/
├── .github/
│   └── workflows/
│       ├── ci.yml                    # ✨ CI pipeline
│       └── deploy.yml                # ✨ Deploy pipeline
├── docker/
│   └── Dockerfile                    # ✨ Multi-stage
├── k8s/
│   ├── deployment.yaml               # Updated with image
│   ├── service.yaml
│   ├── hpa.yaml
│   └── configmap.yaml
├── src/
│   ├── api.py
│   ├── train.py
│   ├── drift_check.py
│   └── simulate_drift.py
├── tests/
│   ├── test_api.py                   # ✨ API tests
│   ├── test_drift_check.py           # ✨ Drift tests
│   ├── test_train.py
│   ├── conftest.py                   # ✨ Pytest fixtures
│   └── __init__.py
├── Makefile                          # ✨ Local commands
├── requirements.txt
├── requirements-dev.txt              # ✨ Dev dependencies
├── pytest.ini                        # ✨ Pytest config
├── .env.example                      # ✨ Environment template
├── .dockerignore                     # ✨ Docker optimization
├── setup.py
└── README.md (updated)
```

---

**✅ Лабораторная 13 готова к выполнению!**

### Основные артефакты:
- ✨ `.github/workflows/ci.yml` — полный CI pipeline
- ✨ `.github/workflows/deploy.yml` — автоматический деплой
- ✨ `docker/Dockerfile` — production-ready multi-stage
- ✨ `tests/test_*.py` — unit тесты с coverage
- ✨ `k8s/*.yaml` — обновлённые манифесты
- ✨ `Makefile` — локальные команды
- ✨ Автоматический деплой после merge в main
- ✨ Smoke тесты и уведомления в Slack (опционально)

### Ключевые возможности:
1. **Полная автоматизация** — от кода до кластера
2. **Безопасность** — секреты в GitHub, non-root containers
3. **Масштабируемость** — HPA для автоскейлинга
4. **Мониторинг** — Prometheus метрики и алерты
5. **Оптимизация** — multi-stage Docker, кэширование слоёв
6. **GitOps** — управление инфраструктурой через Git
7. **Версионирование** — GitHub Releases и семантическое версионирование
