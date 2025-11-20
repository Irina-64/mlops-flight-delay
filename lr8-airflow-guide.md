# ЛР8: Оркестрация пайплайна (Apache Airflow)
## Пошаговое описание для проекта mlops-flight-delay

---

## Часть 1: Установка и настройка Airflow

### Шаг 1.1 — Установка Apache Airflow

```bash
# Установите Airflow (это может занять время)
pip install apache-airflow[core]==2.7.0
pip install apache-airflow-providers-apache-spark==4.0.0

# Или добавьте в requirements.txt
echo "apache-airflow[core]==2.7.0" >> requirements.txt
echo "apache-airflow-providers-apache-spark==4.0.0" >> requirements.txt

pip install -r requirements.txt
```

### Шаг 1.2 — Инициализация Airflow home directory

```bash
# Установите AIRFLOW_HOME переменную
export AIRFLOW_HOME=~/airflow

# Инициализируйте БД Airflow (SQLite по умолчанию)
airflow db init

# Создайте учетную запись администратора
airflow users create \
    --username admin \
    --firstname Admin \
    --lastname User \
    --role Admin \
    --email admin@example.com \
    --password admin123
```

### Шаг 1.3 — Проверьте установку

```bash
# Проверьте версию
airflow version

# Запустите scheduler и webserver
airflow webserver --port 8080  # В одном терминале
airflow scheduler               # В другом терминале

# Откройте http://localhost:8080
# Логин: admin / Пароль: admin123
```

---

## Часть 2: Структура проекта для Airflow

### Шаг 2.1 — Создайте директорию для DAG'ов

```bash
# Структура проекта
mlops-flight-delay/
├── dags/                      # ← DAG'ы Airflow
│   └── ml_pipeline_dag.py     # Основной DAG
├── src/
│   ├── preprocess.py
│   ├── train.py
│   ├── evaluate.py
│   ├── predict.py
│   ├── api.py
│   └── utils.py
├── data/
│   ├── raw/
│   └── processed/
├── models/
├── reports/
├── tests/
├── docker-compose.yml         # Для локального Airflow
├── requirements.txt
└── README.md
```

### Шаг 2.2 — Создайте папку для DAG'ов

```bash
mkdir -p dags
touch dags/__init__.py
```

---

## Часть 3: Создание основного DAG'а

### Шаг 3.1 — Создайте простой DAG с тремя тасками

**Файл:** `dags/ml_pipeline_dag.py`

```python
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.utils.task_group import TaskGroup

import sys
sys.path.insert(0, '/home/user/mlops-flight-delay')  # Путь к проекту

from src.preprocess import load_and_clean_data
from src.train import train_model
from src.evaluate import evaluate_model

# ============= КОНФИГУРАЦИЯ DAG'а =============

default_args = {
    'owner': 'ml-team',
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
    'start_date': datetime(2025, 1, 1),
    'email_on_failure': False,
    'email_on_retry': False,
}

dag = DAG(
    dag_id='ml_flight_delay_pipeline',
    default_args=default_args,
    description='ML pipeline для предсказания задержки рейсов',
    schedule_interval='@daily',  # Запускается каждый день в 00:00
    catchup=False,
    tags=['ml', 'flight-delay', 'production'],
)

# ============= PYTHON ФУНКЦИИ ДЛЯ ТАСК'ОВ =============

def preprocess_data(**context):
    """Задача 1: Предобработка данных"""
    print("=" * 50)
    print("Начинаем предобработку данных...")
    print("=" * 50)
    
    # Загружаем данные
    df = load_and_clean_data('data/raw/flights.csv')
    
    # Сохраняем обработанные данные
    df.to_csv('data/processed/flights_processed.csv', index=False)
    
    print(f"✓ Данные обработаны. Размер: {df.shape}")
    print(f"✓ Сохранено в: data/processed/flights_processed.csv")
    
    # Пушим метрики в XCom (для следующих таск'ов)
    context['task_instance'].xcom_push(
        key='rows_processed',
        value=len(df)
    )
    context['task_instance'].xcom_push(
        key='columns_count',
        value=len(df.columns)
    )

def train_model_task(**context):
    """Задача 2: Обучение модели"""
    print("=" * 50)
    print("Начинаем обучение модели...")
    print("=" * 50)
    
    # Получаем информацию из предыдущей таски
    ti = context['task_instance']
    rows = ti.xcom_pull(task_ids='preprocess_data', key='rows_processed')
    
    print(f"Используем {rows} примеров для обучения")
    
    # Загружаем обработанные данные
    import pandas as pd
    df = pd.read_csv('data/processed/flights_processed.csv')
    
    # Разделяем на train/test
    from sklearn.model_selection import train_test_split
    X = df.drop('dep_delay', axis=1)
    y = df['dep_delay']
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    # Тренируем модель
    model = train_model(X_train, y_train)
    
    # Сохраняем модель
    import joblib
    joblib.dump(model, 'models/flight_delay_model.pkl')
    
    print(f"✓ Модель обучена и сохранена")
    
    # Пушим информацию о модели
    ti.xcom_push(key='model_version', value='v1')
    ti.xcom_push(key='train_samples', value=len(X_train))

def evaluate_model_task(**context):
    """Задача 3: Оценка модели"""
    print("=" * 50)
    print("Начинаем оценку модели...")
    print("=" * 50)
    
    ti = context['task_instance']
    model_version = ti.xcom_pull(task_ids='train_model', key='model_version')
    train_samples = ti.xcom_pull(task_ids='train_model', key='train_samples')
    
    print(f"Оцениваем модель {model_version} (обучена на {train_samples} примерах)")
    
    # Загружаем данные
    import pandas as pd
    df = pd.read_csv('data/processed/flights_processed.csv')
    
    # Разделяем
    from sklearn.model_selection import train_test_split
    X = df.drop('dep_delay', axis=1)
    y = df['dep_delay']
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    # Загружаем обученную модель
    import joblib
    model = joblib.load('models/flight_delay_model.pkl')
    
    # Оцениваем
    metrics = evaluate_model(model, X_test, y_test)
    
    print(f"Метрики:")
    print(f"  - Accuracy: {metrics.get('accuracy', 'N/A'):.3f}")
    print(f"  - F1 Score: {metrics.get('f1', 'N/A'):.3f}")
    print(f"  - MAE: {metrics.get('mae', 'N/A'):.3f}")
    
    # Сохраняем метрики
    import json
    with open('reports/metrics.json', 'w') as f:
        json.dump(metrics, f, indent=2)
    
    # Пушим метрики
    ti.xcom_push(key='accuracy', value=metrics.get('accuracy', 0))
    ti.xcom_push(key='f1', value=metrics.get('f1', 0))

def validate_model(**context):
    """Задача 4: Валидация модели"""
    print("=" * 50)
    print("Валидируем модель...")
    print("=" * 50)
    
    ti = context['task_instance']
    accuracy = ti.xcom_pull(task_ids='evaluate_model', key='accuracy')
    
    print(f"Accuracy модели: {accuracy:.3f}")
    
    # Проверяем что accuracy выше baseline
    MIN_ACCURACY = 0.75
    if accuracy < MIN_ACCURACY:
        raise ValueError(
            f"Model accuracy {accuracy:.3f} is below minimum {MIN_ACCURACY}. "
            "Model will not be deployed."
        )
    
    print(f"✓ Модель валидна! Accuracy > {MIN_ACCURACY}")

# ============= ОПРЕДЕЛЕНИЕ ТАСК'ОВ =============

# Таска 1: Предобработка
task_preprocess = PythonOperator(
    task_id='preprocess_data',
    python_callable=preprocess_data,
    dag=dag,
)

# Таска 2: Обучение
task_train = PythonOperator(
    task_id='train_model',
    python_callable=train_model_task,
    dag=dag,
)

# Таска 3: Оценка
task_evaluate = PythonOperator(
    task_id='evaluate_model',
    python_callable=evaluate_model_task,
    dag=dag,
)

# Таска 4: Валидация
task_validate = PythonOperator(
    task_id='validate_model',
    python_callable=validate_model,
    dag=dag,
)

# Таска 5: Логирование успеха
task_success = BashOperator(
    task_id='log_success',
    bash_command='echo "✓ ML Pipeline completed successfully!" && date',
    dag=dag,
)

# ============= ОПРЕДЕЛЕНИЕ ЗАВИСИМОСТЕЙ (DAG) =============

# Порядок выполнения
task_preprocess >> task_train >> task_evaluate >> task_validate >> task_success

"""
Граф зависимостей:
preprocess_data → train_model → evaluate_model → validate_model → log_success
"""
```

---

## Часть 4: Расширенный DAG с обработкой ошибок

### Шаг 4.1 — Создайте продвинутый DAG с обработкой ошибок

**Файл:** `dags/ml_pipeline_advanced.py`

```python
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.email import EmailOperator
from airflow.utils.task_group import TaskGroup
from airflow.exceptions import AirflowException

# ============= КОНФИГУРАЦИЯ =============

default_args = {
    'owner': 'ml-team',
    'retries': 3,
    'retry_delay': timedelta(minutes=5),
    'start_date': datetime(2025, 1, 1),
    'email_on_failure': True,
    'email_on_retry': False,
    'email': 'ml-team@company.com',
}

dag = DAG(
    dag_id='ml_flight_delay_pipeline_v2',
    default_args=default_args,
    description='Advanced ML pipeline с обработкой ошибок',
    schedule_interval='@daily',
    max_active_runs=1,  # Одновременно запускается только одна версия
    catchup=False,
    tags=['ml', 'flight-delay', 'advanced'],
)

# ============= ФУНКЦИИ =============

def check_data_quality(**context):
    """Проверка качества данных перед обработкой"""
    print("Проверяем качество данных...")
    
    import pandas as pd
    df = pd.read_csv('data/raw/flights.csv')
    
    # Проверяем пропуски
    missing_pct = df.isnull().sum().max() / len(df) * 100
    if missing_pct > 50:
        raise AirflowException(f"Too many missing values: {missing_pct:.1f}%")
    
    # Проверяем размер
    if len(df) < 1000:
        raise AirflowException(f"Dataset too small: {len(df)} rows")
    
    print(f"✓ Data quality OK. Rows: {len(df)}, Missing: {missing_pct:.1f}%")

def preprocess_data_v2(**context):
    """Предобработка с более строгой обработкой ошибок"""
    print("Предобработка данных (v2)...")
    
    try:
        import pandas as pd
        df = pd.read_csv('data/raw/flights.csv')
        
        # Очистка
        df = df.dropna(thresh=len(df) * 0.8, axis=1)
        df = df.dropna()
        
        # Валидация
        if 'dep_delay' not in df.columns:
            raise ValueError("Missing target column 'dep_delay'")
        
        # Сохранение
        df.to_csv('data/processed/flights_processed.csv', index=False)
        
        context['task_instance'].xcom_push(
            key='data_shape',
            value=f"{df.shape[0]}x{df.shape[1]}"
        )
        
        print(f"✓ Data preprocessed: {df.shape}")
        
    except Exception as e:
        raise AirflowException(f"Preprocessing failed: {str(e)}")

def train_with_cv(**context):
    """Обучение с cross-validation"""
    print("Обучение модели с CV...")
    
    import pandas as pd
    import joblib
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import cross_val_score
    
    df = pd.read_csv('data/processed/flights_processed.csv')
    
    X = df.drop('dep_delay', axis=1)
    y = df['dep_delay']
    
    model = RandomForestClassifier(n_estimators=100, random_state=42)
    
    # Cross-validation
    scores = cross_val_score(model, X, y, cv=5, scoring='f1_macro')
    
    print(f"CV Scores: {scores}")
    print(f"Mean CV Score: {scores.mean():.3f} (+/- {scores.std():.3f})")
    
    # Полное обучение
    model.fit(X, y)
    joblib.dump(model, 'models/flight_delay_model.pkl')
    
    context['task_instance'].xcom_push(key='cv_mean', value=float(scores.mean()))
    context['task_instance'].xcom_push(key='cv_std', value=float(scores.std()))

def generate_report(**context):
    """Генерирование отчета"""
    print("Генерируем отчет...")
    
    ti = context['task_instance']
    data_shape = ti.xcom_pull(task_ids='preprocess_data', key='data_shape')
    cv_mean = ti.xcom_pull(task_ids='train_model', key='cv_mean')
    cv_std = ti.xcom_pull(task_ids='train_model', key='cv_std')
    
    report = f"""
    ============ ML PIPELINE REPORT ============
    
    Execution Date: {context['execution_date']}
    DAG: {context['dag'].dag_id}
    
    DATA STATISTICS:
    - Shape: {data_shape}
    
    MODEL PERFORMANCE:
    - CV Mean Score: {cv_mean:.3f}
    - CV Std: {cv_std:.3f}
    
    STATUS: ✓ SUCCESS
    
    ==========================================
    """
    
    print(report)
    
    # Сохраняем отчет
    with open('reports/pipeline_report.txt', 'w') as f:
        f.write(report)

# ============= TASK GROUPS =============

with TaskGroup("data_pipeline", dag=dag) as data_group:
    check_quality = PythonOperator(
        task_id='check_data_quality',
        python_callable=check_data_quality,
    )
    
    preprocess = PythonOperator(
        task_id='preprocess_data',
        python_callable=preprocess_data_v2,
    )
    
    check_quality >> preprocess

with TaskGroup("model_pipeline", dag=dag) as model_group:
    train = PythonOperator(
        task_id='train_model',
        python_callable=train_with_cv,
    )
    
    report = PythonOperator(
        task_id='generate_report',
        python_callable=generate_report,
    )
    
    train >> report

# ============= DAG FLOW =============

data_group >> model_group
```

---

## Часть 5: Запуск Airflow локально

### Шаг 5.1 — Запустите DAG в двух терминалах

**Терминал 1 - Scheduler:**
```bash
export AIRFLOW_HOME=~/airflow
airflow scheduler
```

**Терминал 2 - Webserver:**
```bash
export AIRFLOW_HOME=~/airflow
airflow webserver --port 8080
```

### Шаг 5.2 — Откройте Airflow UI

```
http://localhost:8080
```

### Шаг 5.3 — Активируйте DAG

1. Найдите DAG в списке (`ml_flight_delay_pipeline`)
2. Нажмите на кнопку `OFF` чтобы включить DAG
3. DAG начнет выполняться по расписанию

### Шаг 5.4 — Мониторьте выполнение

- **DAGs** вкладка — список всех DAG'ов
- Кликните на DAG → посмотрите граф
- **Tree View** — иерархия выполнения
- **Graph View** — визуальный граф зависимостей
- **Logs** — логи каждой таски

---

## Часть 6: Docker Compose для локального Airflow

### Шаг 6.1 — Создайте Docker Compose файл

**Файл:** `docker-compose.yml`

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:13
    environment:
      POSTGRES_USER: airflow
      POSTGRES_PASSWORD: airflow
      POSTGRES_DB: airflow
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  airflow-webserver:
    image: apache/airflow:2.7.0-python3.10
    depends_on:
      - postgres
    environment:
      AIRFLOW__CORE__EXECUTOR: LocalExecutor
      AIRFLOW__CORE__SQL_ALCHEMY_CONN: postgresql+psycopg2://airflow:airflow@postgres/airflow
      AIRFLOW__CORE__FERNET_KEY: your_fernet_key_here
      AIRFLOW__CORE__LOAD_EXAMPLES: 'false'
      AIRFLOW__CORE__DAGS_FOLDER: /airflow/dags
    ports:
      - "8080:8080"
    volumes:
      - ./dags:/airflow/dags
      - ./src:/airflow/src
      - ./data:/airflow/data
      - ./models:/airflow/models
      - ./reports:/airflow/reports
    command: webserver

  airflow-scheduler:
    image: apache/airflow:2.7.0-python3.10
    depends_on:
      - postgres
    environment:
      AIRFLOW__CORE__EXECUTOR: LocalExecutor
      AIRFLOW__CORE__SQL_ALCHEMY_CONN: postgresql+psycopg2://airflow:airflow@postgres/airflow
      AIRFLOW__CORE__FERNET_KEY: your_fernet_key_here
      AIRFLOW__CORE__LOAD_EXAMPLES: 'false'
      AIRFLOW__CORE__DAGS_FOLDER: /airflow/dags
    volumes:
      - ./dags:/airflow/dags
      - ./src:/airflow/src
      - ./data:/airflow/data
      - ./models:/airflow/models
      - ./reports:/airflow/reports
    command: scheduler

volumes:
  postgres_data:
```

### Шаг 6.2 — Запустите Docker Compose

```bash
# Запустите контейнеры
docker-compose up -d

# Проверьте статус
docker-compose ps

# Посмотрите логи
docker-compose logs -f airflow-scheduler

# Откройте http://localhost:8080

# Остановите
docker-compose down
```

---

## Часть 7: Интеграция с мониторингом

### Шаг 7.1 — Создайте файл для логирования метрик

**Файл:** `dags/ml_monitoring_dag.py`

```python
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
import json

default_args = {
    'owner': 'ml-team',
    'start_date': datetime(2025, 1, 1),
}

dag = DAG(
    dag_id='ml_monitoring_pipeline',
    default_args=default_args,
    description='DAG для мониторинга качества модели',
    schedule_interval='@daily',
    catchup=False,
    tags=['monitoring'],
)

def check_model_drift(**context):
    """Проверка data drift"""
    print("Проверяем data drift...")
    
    import pandas as pd
    from scipy.stats import ks_2samp
    import numpy as np
    
    # Загружаем training data (reference)
    train_data = pd.read_csv('data/raw/flights.csv')
    
    # Загружаем текущие данные
    current_data = pd.read_csv('data/processed/flights_processed.csv')
    
    # Проверяем drift по ключевым признакам
    features_to_check = ['dep_hour', 'distance']
    
    drifts = {}
    for feature in features_to_check:
        if feature in train_data.columns and feature in current_data.columns:
            stat, p_value = ks_2samp(train_data[feature].dropna(), 
                                     current_data[feature].dropna())
            
            drifted = p_value < 0.05
            drifts[feature] = {
                'statistic': float(stat),
                'p_value': float(p_value),
                'drifted': bool(drifted)
            }
            
            print(f"  {feature}: {'DRIFT!' if drifted else 'OK'} (p-value: {p_value:.4f})")
    
    # Сохраняем результаты
    with open('reports/drift_report.json', 'w') as f:
        json.dump(drifts, f, indent=2)
    
    context['task_instance'].xcom_push(key='drifts', value=drifts)

def alert_if_drift(**context):
    """Отправляем алерт если есть drift"""
    ti = context['task_instance']
    drifts = ti.xcom_pull(task_ids='check_drift', key='drifts')
    
    has_drift = any(d['drifted'] for d in drifts.values())
    
    if has_drift:
        print("⚠️  DATA DRIFT DETECTED!")
        print("Дрифт найден в признаках:")
        for feature, data in drifts.items():
            if data['drifted']:
                print(f"  - {feature} (p-value: {data['p_value']:.4f})")
    else:
        print("✓ No data drift detected")

# Таски
task_check_drift = PythonOperator(
    task_id='check_drift',
    python_callable=check_model_drift,
    dag=dag,
)

task_alert = PythonOperator(
    task_id='alert_if_drift',
    python_callable=alert_if_drift,
    dag=dag,
)

task_check_drift >> task_alert
```

---

## Часть 8: Управление DAG'ами из CLI

### Шаг 8.1 — Основные команды Airflow

```bash
# Список всех DAG'ов
airflow dags list

# Информация о DAG'е
airflow dags info ml_flight_delay_pipeline

# Тесты DAG'а (проверка синтаксиса)
airflow dags test ml_flight_delay_pipeline 2025-01-01

# Запуск DAG'а вручную
airflow dags trigger ml_flight_delay_pipeline

# Список таск'ов в DAG'е
airflow tasks list ml_flight_delay_pipeline

# Тест конкретной таски
airflow tasks test ml_flight_delay_pipeline preprocess_data 2025-01-01

# Просмотр логов таски
airflow tasks logs ml_flight_delay_pipeline preprocess_data 2025-01-01

# Перезапуск DAG'а
airflow dags backfill ml_flight_delay_pipeline \
    --start-date 2025-01-01 \
    --end-date 2025-01-10

# Паузировать DAG
airflow dags pause ml_flight_delay_pipeline

# Возобновить DAG
airflow dags unpause ml_flight_delay_pipeline

# Удалить DAG
airflow dags delete ml_flight_delay_pipeline
```

---

## Часть 9: Отладка и логирование

### Шаг 9.1 — Добавьте детальное логирование

**Файл:** `dags/ml_pipeline_with_logging.py`

```python
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
import logging

# Получаем logger Airflow
logger = logging.getLogger(__name__)

default_args = {
    'owner': 'ml-team',
    'start_date': datetime(2025, 1, 1),
}

dag = DAG(
    dag_id='ml_flight_delay_with_logging',
    default_args=default_args,
    schedule_interval='@daily',
    catchup=False,
)

def task_with_logging(**context):
    """Таска с детальным логированием"""
    
    logger.info("=" * 50)
    logger.info("Начинаем обработку...")
    logger.info("=" * 50)
    
    execution_date = context['execution_date']
    logger.info(f"Execution date: {execution_date}")
    
    try:
        # Ваш код
        logger.info("Загружаем данные...")
        import pandas as pd
        df = pd.read_csv('data/raw/flights.csv')
        
        logger.info(f"✓ Данные загружены: {df.shape}")
        logger.info(f"  Columns: {list(df.columns)}")
        logger.info(f"  Memory usage: {df.memory_usage(deep=True).sum() / 1024**2:.2f} MB")
        
        # Статистика
        logger.debug(f"Descriptive stats:\n{df.describe()}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {str(e)}", exc_info=True)
        raise
    
    logger.info("✓ Таска завершена успешно!")

task = PythonOperator(
    task_id='process_with_logging',
    python_callable=task_with_logging,
    dag=dag,
)
```

---

## Часть 10: Контрольный список завершения ЛР8

**Базовые требования:**
- [ ] Установлен Apache Airflow 2.7+
- [ ] Создана папка `dags/`
- [ ] Написан основной DAG (`ml_pipeline_dag.py`) с 5 тасками
- [ ] DAG содержит: preprocess → train → evaluate → validate → success
- [ ] Используется XCom для передачи данных между тасками
- [ ] DAG проходит тест: `airflow dags test`
- [ ] Airflow UI доступен на http://localhost:8080
- [ ] DAG выполняется в Airflow UI без ошибок

**Расширенные требования:**
- [ ] Создан расширенный DAG v2 с обработкой ошибок
- [ ] Используются TaskGroup'ы для организации
- [ ] Добавлена проверка качества данных
- [ ] Добавлено логирование и мониторинг drift
- [ ] Docker Compose файл для локального развертывания
- [ ] Использованы попытки повтора (retries)
- [ ] Отправка уведомлений при ошибках

**Документация и тестирование:**
- [ ] README обновлен с инструкциями Airflow
- [ ] Все команды Airflow CLI протестированы
- [ ] Логи понятны и информативны
- [ ] Граф DAG'а правильно отображается в UI

---

## Шпаргалка команд Airflow

```bash
# Установка
pip install apache-airflow[core]==2.7.0
export AIRFLOW_HOME=~/airflow
airflow db init

# Запуск
airflow webserver --port 8080  # Terminal 1
airflow scheduler               # Terminal 2

# DAG команды
airflow dags list
airflow dags test DAG_ID EXECUTION_DATE
airflow dags trigger DAG_ID
airflow dags pause DAG_ID
airflow dags unpause DAG_ID

# Task команды
airflow tasks list DAG_ID
airflow tasks test DAG_ID TASK_ID EXECUTION_DATE
airflow tasks logs DAG_ID TASK_ID EXECUTION_DATE

# Docker
docker-compose up -d
docker-compose logs -f airflow-scheduler
docker-compose down
```

---

## Полезные ссылки

- **Airflow Documentation:** https://airflow.apache.org/docs/
- **Airflow Concepts:** https://airflow.apache.org/docs/apache-airflow/stable/concepts/
- **Operators:** https://airflow.apache.org/docs/apache-airflow/stable/howto/operator/index.html
- **Best Practices:** https://airflow.apache.org/docs/apache-airflow/stable/best-practices.html
- **XCom:** https://airflow.apache.org/docs/apache-airflow/stable/concepts/xcom.html

---

**Версия: 1.0 | Ноябрь 2025**
