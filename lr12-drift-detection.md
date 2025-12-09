# Лабораторная 12: Детекция дрейфа и автоматическая реакция

## 📋 Цель работы

Реализовать систему автоматического обнаружения дрейфа данных (feature drift и performance drift) и триггеризации переобучения модели при превышении порогов.

**Ключевые задачи:**
- Реализовать скрипт проверки дрейфа через PSI (Population Stability Index) или KS-тест
- Добавить регулярную проверку в Airflow DAG или cron
- Автоматически триггеризировать переобучение при обнаружении дрейфа
- Демонстрация работы с синтетическим сдвигом данных

---

## 📚 Требования

### Зависимости
```bash
# Python пакеты (добавить в requirements.txt)
pip install evidently==0.4.10  # или самописный PSI
pip install apache-airflow==2.7.0  # если используется Airflow
pip install numpy scipy pandas scikit-learn
pip install mlflow>=2.0.0  # опционально для версионирования
pip install python-dateutil
```

### Инфраструктура
- Python 3.9+
- PostgreSQL или SQLite (для хранения метрик дрейфа)
- Airflow (рекомендуется) или системный cron
- MLflow (опционально для версионирования моделей)
- Prometheus + Grafana (из ЛР11, для мониторинга)

### Структура файлов после ЛР11
```
mlops-flight-delay/
├── src/
│   ├── api.py                     # API с метриками (ЛР11)
│   ├── train.py                   # Обучение модели (ЛР6-10)
│   ├── drift_check.py             # ✨ НОВЫЙ: Проверка дрейфа
│   └── simulate_drift.py           # ✨ НОВЫЙ: Генерация дрейфа
├── dags/
│   └── flight_delay_drift_dag.py  # ✨ НОВЫЙ: DAG с контролем дрейфа
├── models/
│   └── flight_delay_model.pkl
├── reports/
│   ├── drift_report.json           # ✨ НОВЫЙ: Отчёт о дрейфе
│   └── drift_history.csv           # ✨ НОВЫЙ: История дрейфа
├── data/
│   ├── train.csv                   # Обучающий набор (baseline)
│   └── production_recent.csv        # Недавние production данные
├── prometheus/
│   └── alert_rules.yml             # Добавить drift alerts
├── docker-compose.yml              # Добавить Airflow service
└── k8s/
    └── drift_check_cronjob.yaml    # ✨ НОВЫЙ: K8s CronJob
```

---

## 🔧 Раздел 1: Реализация скрипта проверки дрейфа

### 1.1 Создать `src/drift_check.py` — основной модуль

Файл `src/drift_check.py`:

```python
"""
Модуль проверки дрейфа (Feature Drift & Performance Drift Detection)
Использует PSI (Population Stability Index) для сравнения распределений
"""

import json
import pickle
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Tuple, List, Any
from scipy import stats
import logging
import sqlite3

# ============ ЛОГИРОВАНИЕ ============
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/drift_check.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============ КОНФИГИ ============
DRIFT_CONFIG = {
    'psi_threshold': 0.25,           # Порог PSI для feature drift
    'ks_threshold': 0.15,             # Порог KS-теста
    'performance_threshold': 0.05,    # Падение ROC-AUC на 5% → дрейф
    'min_samples_production': 100,    # Минимум примеров для проверки
}

FEATURE_RANGES = {
    'duration': (10, 500),            # Минуты
    'departure_hour': (0, 23),        # Часы
    'days_since': (0, 365),           # Дни
    'origin_hash': (0, 100),          # Хэш аэропорта
    'destination_hash': (0, 100),
}

# ============ ФУНКЦИИ ДРЕЙФА ============

def calculate_psi(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
    """
    Вычислить PSI (Population Stability Index)
    
    PSI = Σ (actual_pct - expected_pct) * ln(actual_pct / expected_pct)
    
    PSI интерпретация:
    < 0.1   → нет дрейфа
    0.1-0.25 → малый дрейф (требует мониторинга)
    > 0.25   → значительный дрейф (требует переобучения)
    
    Args:
        expected: Базовое распределение (обучающий набор)
        actual:   Актуальное распределение (production)
        bins:     Количество бинов для дискретизации
    
    Returns:
        PSI значение
    """
    # Обработать NaN и бесконечности
    expected = expected[np.isfinite(expected)]
    actual = actual[np.isfinite(actual)]
    
    if len(expected) == 0 or len(actual) == 0:
        logger.warning("Empty arrays in PSI calculation")
        return np.nan
    
    # Совместные диапазоны
    min_val = min(expected.min(), actual.min())
    max_val = max(expected.max(), actual.max())
    
    # Дискретизация
    edges = np.linspace(min_val, max_val, bins + 1)
    expected_counts = np.histogram(expected, bins=edges)[0]
    actual_counts = np.histogram(actual, bins=edges)[0]
    
    # Нормализация
    expected_pct = expected_counts / expected_counts.sum()
    actual_pct = actual_counts / actual_counts.sum()
    
    # Добавить малую константу для избежания ln(0)
    epsilon = 1e-10
    expected_pct = np.clip(expected_pct, epsilon, 1)
    actual_pct = np.clip(actual_pct, epsilon, 1)
    
    # Вычисление PSI
    psi = np.sum((actual_pct - expected_pct) * np.log(actual_pct / expected_pct))
    
    return float(psi)


def calculate_ks_statistic(expected: np.ndarray, actual: np.ndarray) -> float:
    """
    Колмогоров-Смирнов тест для сравнения CDF двух распределений
    
    Возвращает D-статистику (максимальное расстояние между CDF)
    
    Интерпретация:
    D < 0.1   → распределения похожи
    0.1-0.15  → умеренное отличие
    D > 0.15  → значительное отличие
    """
    expected = expected[np.isfinite(expected)]
    actual = actual[np.isfinite(actual)]
    
    if len(expected) == 0 or len(actual) == 0:
        logger.warning("Empty arrays in KS test")
        return np.nan
    
    ks_stat, p_value = stats.ks_2samp(expected, actual)
    
    logger.info(f"KS test: D={ks_stat:.4f}, p-value={p_value:.6f}")
    
    return float(ks_stat)


def load_baseline_data(path: str = 'data/train.csv') -> pd.DataFrame:
    """Загрузить базовый обучающий набор"""
    logger.info(f"Loading baseline data from {path}")
    df = pd.read_csv(path)
    logger.info(f"Baseline shape: {df.shape}")
    return df


def load_production_data(
    path: str = 'data/production_recent.csv',
    hours: int = 24
) -> pd.DataFrame:
    """
    Загрузить недавние production данные
    
    Args:
        path: Путь к файлу
        hours: Если есть timestamp, берём последние N часов
    
    Returns:
        DataFrame с production данными
    """
    logger.info(f"Loading production data from {path}")
    df = pd.read_csv(path)
    
    # Если есть timestamp, фильтровать
    if 'timestamp' in df.columns:
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        df = df[df['timestamp'] >= cutoff]
        logger.info(f"Filtered to last {hours}h: {len(df)} records")
    
    logger.info(f"Production data shape: {df.shape}")
    return df


def check_feature_drift(
    baseline_df: pd.DataFrame,
    production_df: pd.DataFrame,
    features: List[str] = None
) -> Dict[str, Dict[str, float]]:
    """
    Проверить дрейф для каждого признака
    
    Returns:
        {
            'duration': {'psi': 0.18, 'ks': 0.12, 'drifted': False},
            'departure_hour': {'psi': 0.42, 'ks': 0.21, 'drifted': True},
            ...
        }
    """
    if features is None:
        features = ['duration', 'departure_hour', 'days_since', 'origin_hash', 'destination_hash']
    
    logger.info(f"Checking feature drift for {len(features)} features")
    
    drift_results = {}
    
    for feature in features:
        if feature not in baseline_df.columns or feature not in production_df.columns:
            logger.warning(f"Feature {feature} not in data")
            continue
        
        baseline_vals = baseline_df[feature].dropna().values.astype(float)
        production_vals = production_df[feature].dropna().values.astype(float)
        
        if len(production_vals) < DRIFT_CONFIG['min_samples_production']:
            logger.warning(
                f"Not enough production samples for {feature}: "
                f"{len(production_vals)} < {DRIFT_CONFIG['min_samples_production']}"
            )
            continue
        
        # Вычисление метрик дрейфа
        psi = calculate_psi(baseline_vals, production_vals)
        ks = calculate_ks_statistic(baseline_vals, production_vals)
        
        drifted = (
            psi > DRIFT_CONFIG['psi_threshold'] or 
            ks > DRIFT_CONFIG['ks_threshold']
        )
        
        drift_results[feature] = {
            'psi': psi,
            'ks': ks,
            'drifted': drifted,
            'baseline_mean': float(np.mean(baseline_vals)),
            'baseline_std': float(np.std(baseline_vals)),
            'production_mean': float(np.mean(production_vals)),
            'production_std': float(np.std(production_vals)),
        }
        
        logger.info(
            f"{feature}: PSI={psi:.4f}, KS={ks:.4f}, "
            f"Drifted={drifted}"
        )
    
    return drift_results


def check_performance_drift(
    model_path: str = 'models/flight_delay_model.pkl',
    baseline_df: pd.DataFrame = None,
    production_df: pd.DataFrame = None,
) -> Dict[str, Any]:
    """
    Проверить дрейф производительности модели
    
    Сравнивает ROC-AUC на baseline vs production
    """
    logger.info("Checking performance drift")
    
    try:
        with open(model_path, 'rb') as f:
            model = pickle.load(f)
    except Exception as e:
        logger.error(f"Failed to load model: {e}")
        return {'error': str(e), 'performance_drifted': False}
    
    # Подготовка признаков (адаптировать под вашу модель)
    feature_cols = ['duration', 'departure_hour', 'days_since', 'origin_hash', 'destination_hash']
    
    def get_features(df):
        if 'target' in df.columns:
            X = df[feature_cols].fillna(0).values
            y = df['target'].values
            return X, y
        return None, None
    
    # Получить метрики baseline
    X_baseline, y_baseline = get_features(baseline_df)
    if X_baseline is None:
        logger.warning("Cannot compute baseline metrics")
        return {'performance_drifted': False}
    
    try:
        y_pred_baseline = model.predict_proba(X_baseline)[:, 1]
        from sklearn.metrics import roc_auc_score
        baseline_auc = roc_auc_score(y_baseline, y_pred_baseline)
        logger.info(f"Baseline ROC-AUC: {baseline_auc:.4f}")
    except Exception as e:
        logger.error(f"Error computing baseline metrics: {e}")
        baseline_auc = None
    
    # Получить метрики production
    X_production, y_production = get_features(production_df)
    if X_production is None:
        logger.warning("Cannot compute production metrics")
        return {'performance_drifted': False}
    
    try:
        y_pred_production = model.predict_proba(X_production)[:, 1]
        production_auc = roc_auc_score(y_production, y_pred_production)
        logger.info(f"Production ROC-AUC: {production_auc:.4f}")
    except Exception as e:
        logger.error(f"Error computing production metrics: {e}")
        production_auc = None
    
    # Сравнение
    if baseline_auc and production_auc:
        auc_drop = baseline_auc - production_auc
        performance_drifted = auc_drop > DRIFT_CONFIG['performance_threshold']
        
        logger.info(
            f"AUC drop: {auc_drop:.4f} ({auc_drop/baseline_auc*100:.1f}%), "
            f"Drifted={performance_drifted}"
        )
        
        return {
            'baseline_auc': float(baseline_auc),
            'production_auc': float(production_auc),
            'auc_drop': float(auc_drop),
            'auc_drop_pct': float(auc_drop / baseline_auc * 100),
            'performance_drifted': performance_drifted,
        }
    
    return {'performance_drifted': False}


def save_drift_report(
    feature_drift: Dict,
    performance_drift: Dict,
    output_path: str = 'reports/drift_report.json'
) -> None:
    """Сохранить отчёт о дрейфе в JSON"""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    report = {
        'timestamp': datetime.utcnow().isoformat(),
        'feature_drift': feature_drift,
        'performance_drift': performance_drift,
        'overall_drifted': any(
            f.get('drifted', False) for f in feature_drift.values()
        ) or performance_drift.get('performance_drifted', False),
        'config': DRIFT_CONFIG,
    }
    
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    logger.info(f"Drift report saved to {output_path}")
    return report


def log_drift_history(
    report: Dict,
    history_path: str = 'reports/drift_history.csv'
) -> None:
    """Добавить запись в историю дрейфа"""
    Path(history_path).parent.mkdir(parents=True, exist_ok=True)
    
    # Извлечь основные метрики в одну строку
    row = {
        'timestamp': report['timestamp'],
        'overall_drifted': report['overall_drifted'],
    }
    
    # Добавить PSI для каждого признака
    for feature, metrics in report['feature_drift'].items():
        row[f'{feature}_psi'] = metrics.get('psi', np.nan)
        row[f'{feature}_ks'] = metrics.get('ks', np.nan)
    
    # Добавить performance метрики
    row['auc_drop'] = report['performance_drift'].get('auc_drop', np.nan)
    
    df = pd.DataFrame([row])
    
    # Append или create
    if Path(history_path).exists():
        df_history = pd.read_csv(history_path)
        df = pd.concat([df_history, df], ignore_index=True)
    
    df.to_csv(history_path, index=False)
    logger.info(f"History saved to {history_path}")


def should_retrain(report: Dict) -> bool:
    """
    Определить, нужно ли переобучение
    
    Критерии:
    - Обнаружен дрейф в любом признаке
    - Падение производительности > порога
    - Комбинация: несколько признаков имеют PSI > 0.15
    """
    if report['overall_drifted']:
        return True
    
    # Дополнительная эвристика: много признаков с умеренным дрейфом
    moderate_drift_count = sum(
        1 for f in report['feature_drift'].values()
        if 0.15 < f.get('psi', 0) < 0.25
    )
    
    if moderate_drift_count >= 2:
        logger.warning(f"Multiple features with moderate drift ({moderate_drift_count})")
        return True
    
    return False


# ============ ГЛАВНАЯ ФУНКЦИЯ ============

def run_drift_check(
    baseline_path: str = 'data/train.csv',
    production_path: str = 'data/production_recent.csv',
    model_path: str = 'models/flight_delay_model.pkl',
    output_report: str = 'reports/drift_report.json',
    output_history: str = 'reports/drift_history.csv',
) -> Tuple[bool, Dict]:
    """
    Полная проверка дрейфа
    
    Returns:
        (should_retrain, report)
    """
    logger.info("="*60)
    logger.info("STARTING DRIFT CHECK")
    logger.info("="*60)
    
    try:
        # Загрузить данные
        baseline_df = load_baseline_data(baseline_path)
        production_df = load_production_data(production_path)
        
        if len(production_df) < DRIFT_CONFIG['min_samples_production']:
            logger.warning("Not enough production samples")
            return False, {'error': 'insufficient_production_data'}
        
        # Feature drift
        feature_drift = check_feature_drift(baseline_df, production_df)
        
        # Performance drift
        performance_drift = check_performance_drift(
            model_path, baseline_df, production_df
        )
        
        # Сохранить отчёт
        report = save_drift_report(feature_drift, performance_drift, output_report)
        log_drift_history(report, output_history)
        
        # Решение о переобучении
        retrain_needed = should_retrain(report)
        
        logger.info("="*60)
        logger.info(f"DRIFT CHECK COMPLETE")
        logger.info(f"Overall Drifted: {report['overall_drifted']}")
        logger.info(f"Retrain Needed: {retrain_needed}")
        logger.info("="*60)
        
        return retrain_needed, report
    
    except Exception as e:
        logger.error(f"Drift check failed: {e}", exc_info=True)
        return False, {'error': str(e)}


if __name__ == '__main__':
    retrain_needed, report = run_drift_check()
    
    # Вывести результат для Airflow
    if retrain_needed:
        print("RETRAIN_NEEDED=True")
        exit(0)
    else:
        print("RETRAIN_NEEDED=False")
        exit(0)
```

---

## 🔄 Раздел 2: Добавить проверку дрейфа в Prometheus alerts

### 2.1 Обновить `prometheus/alert_rules.yml`

Добавить правила для алертов дрейфа:

```yaml
groups:
- name: flight-delay-api
  interval: 30s
  rules:
  # ... существующие алерты из ЛР11 ...

  # ===== НОВЫЕ АЛЕРТЫ ДРЕЙФА =====
  
  # Alert: Feature Drift Detected
  - alert: FeatureDriftDetected
    expr: flight_delay_api_feature_drift_psi > 0.25
    for: 10m
    labels:
      severity: warning
      component: drift_detection
    annotations:
      summary: "Feature drift detected"
      description: "Feature {{ $labels.feature }} has PSI > 0.25"

  # Alert: Performance Drift (AUC drop)
  - alert: PerformanceDrift
    expr: flight_delay_api_auc_drop > 0.05
    for: 15m
    labels:
      severity: critical
      component: drift_detection
    annotations:
      summary: "Model performance degradation"
      description: "ROC-AUC dropped by {{ $value | humanizePercentage }}"

  # Alert: Retrain Triggered
  - alert: RetrainTriggered
    expr: flight_delay_api_retrain_triggered == 1
    for: 1m
    labels:
      severity: info
      component: drift_detection
    annotations:
      summary: "Automatic retraining started"
      description: "Drift thresholds exceeded, retraining pipeline started"
```

---

## 🌪️ Раздел 3: Симуляция дрейфа

### 3.1 Создать `src/simulate_drift.py`

Файл `src/simulate_drift.py`:

```python
"""
Скрипт для симуляции дрейфа данных в production среде
Изменяет распределение признаков для демонстрации drift detection
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def generate_production_data_with_drift(
    baseline_path: str = 'data/train.csv',
    output_path: str = 'data/production_recent.csv',
    n_samples: int = 500,
    drift_magnitude: float = 1.0,
    drift_features: list = None
) -> None:
    """
    Генерировать production данные с дрейфом
    
    Args:
        baseline_path: Путь к обучающему набору
        output_path: Куда сохранить production данные
        n_samples: Количество примеров
        drift_magnitude: Степень сдвига (0 = нет, 1 = сильный)
        drift_features: Какие признаки сдвинуть
    """
    
    logger.info(f"Generating production data with drift={drift_magnitude}")
    
    # Загрузить baseline
    baseline = pd.read_csv(baseline_path)
    
    if drift_features is None:
        drift_features = ['duration', 'departure_hour']
    
    # Случайная выборка из baseline
    production = baseline.sample(n=n_samples, replace=True).copy()
    
    # Применить дрейф
    if drift_magnitude > 0:
        for feature in drift_features:
            if feature not in production.columns:
                continue
            
            baseline_mean = baseline[feature].mean()
            baseline_std = baseline[feature].std()
            
            # Сдвинуть распределение
            shift = baseline_std * drift_magnitude * 0.5
            production[feature] = production[feature] + shift
            
            logger.info(
                f"Shifted {feature}: "
                f"mean {baseline_mean:.2f} → {production[feature].mean():.2f}"
            )
    
    # Добавить timestamp
    now = datetime.utcnow()
    production['timestamp'] = [
        (now - timedelta(seconds=np.random.randint(0, 86400))).isoformat()
        for _ in range(len(production))
    ]
    
    production.to_csv(output_path, index=False)
    logger.info(f"Saved {len(production)} samples to {output_path}")


def simulate_drift_scenario(scenario: str = 'gradual') -> None:
    """
    Смоделировать различные сценарии дрейфа
    
    Scenarios:
    - 'none': нет дрейфа (baseline)
    - 'gradual': постепенный дрейф (0.3)
    - 'sudden': внезапный дрейф (0.8)
    - 'seasonal': сезонные изменения
    """
    
    logger.info(f"Simulating drift scenario: {scenario}")
    
    if scenario == 'none':
        generate_production_data_with_drift(drift_magnitude=0.0)
    
    elif scenario == 'gradual':
        generate_production_data_with_drift(
            drift_magnitude=0.3,
            drift_features=['duration', 'departure_hour']
        )
    
    elif scenario == 'sudden':
        generate_production_data_with_drift(
            drift_magnitude=0.8,
            drift_features=['duration', 'departure_hour', 'days_since']
        )
    
    elif scenario == 'seasonal':
        baseline = pd.read_csv('data/train.csv')
        production = baseline.sample(n=500, replace=True).copy()
        
        # Смещение по часам вылета (ночные рейсы становятся более задержанными)
        production['departure_hour'] = production['departure_hour'] + 6
        production['departure_hour'] = production['departure_hour'] % 24
        
        production['timestamp'] = [
            (datetime.utcnow() - timedelta(seconds=np.random.randint(0, 86400))).isoformat()
            for _ in range(len(production))
        ]
        
        production.to_csv('data/production_recent.csv', index=False)
        logger.info("Seasonal drift scenario applied")


if __name__ == '__main__':
    import sys
    
    scenario = sys.argv[1] if len(sys.argv) > 1 else 'gradual'
    simulate_drift_scenario(scenario)
```

---

## 🔄 Раздел 4: Airflow DAG с проверкой и реакцией на дрейф

### 4.1 Создать `dags/flight_delay_drift_dag.py`

Файл `dags/flight_delay_drift_dag.py`:

```python
"""
Airflow DAG для проверки дрейфа и автоматического переобучения модели

Schedule: каждый час
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.operators.dummy import DummyOperator
from airflow.sensors.external_task import ExternalTaskSensor
from airflow.models import Variable
from airflow.exceptions import AirflowException
import sys
import json
import logging

# Добавить src в PATH
sys.path.insert(0, '/opt/airflow/dags/../src')

from drift_check import run_drift_check

logger = logging.getLogger(__name__)

# ============ КОНФИГИ ============

DEFAULT_ARGS = {
    'owner': 'data-team',
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
    'email': ['admin@example.com'],
    'email_on_failure': True,
}

DRIFT_CONFIG = {
    'baseline_path': '/data/train.csv',
    'production_path': '/data/production_recent.csv',
    'model_path': '/models/flight_delay_model.pkl',
    'output_report': '/reports/drift_report.json',
}

# ============ PYTHON OPERATTOR ФУНКЦИИ ============

def check_drift_task(**context):
    """
    Запустить проверку дрейфа
    Вернуть результат в XCom для использования в следующих тасках
    """
    logger.info("Starting drift check task")
    
    retrain_needed, report = run_drift_check(
        baseline_path=DRIFT_CONFIG['baseline_path'],
        production_path=DRIFT_CONFIG['production_path'],
        model_path=DRIFT_CONFIG['model_path'],
        output_report=DRIFT_CONFIG['output_report'],
    )
    
    # Сохранить результат в XCom
    context['task_instance'].xcom_push(
        key='retrain_needed',
        value=retrain_needed
    )
    context['task_instance'].xcom_push(
        key='drift_report',
        value=report
    )
    
    logger.info(f"Drift check completed: retrain_needed={retrain_needed}")
    
    return {
        'retrain_needed': retrain_needed,
        'overall_drifted': report.get('overall_drifted', False),
    }


def decide_retrain(**context):
    """
    决定是否启动 retraining DAG
    
    Reads XCom from check_drift_task
    """
    task_instance = context['task_instance']
    
    retrain_needed = task_instance.xcom_pull(
        task_ids='check_drift',
        key='retrain_needed'
    )
    
    report = task_instance.xcom_pull(
        task_ids='check_drift',
        key='drift_report'
    )
    
    logger.info(f"Decision: retrain_needed={retrain_needed}")
    logger.info(f"Report: {json.dumps(report, indent=2, default=str)}")
    
    if retrain_needed:
        logger.warning("DRIFT DETECTED - Triggering retraining pipeline")
        # Это можно заменить на TriggerDagRunOperator
        return 'trigger_retrain'
    else:
        logger.info("No drift detected - skipping retrain")
        return 'skip_retrain'


def trigger_retrain_task(**context):
    """Триггеризировать DAG переобучения"""
    logger.warning("TRIGGERING RETRAIN DAG")
    
    # Вариант 1: Запустить скрипт напрямую
    import subprocess
    result = subprocess.run(
        ['python', '/opt/airflow/src/train.py'],
        capture_output=True,
        text=True
    )
    
    logger.info(f"Train script output: {result.stdout}")
    if result.returncode != 0:
        raise AirflowException(f"Training failed: {result.stderr}")


def register_model_task(**context):
    """Зарегистрировать новую модель в Model Registry"""
    logger.info("Registering retrained model")
    
    import subprocess
    result = subprocess.run(
        [
            'python', '-c',
            'from src.register import register_model; register_model()'
        ],
        capture_output=True,
        text=True,
        cwd='/opt/airflow'
    )
    
    logger.info(f"Model registered: {result.stdout}")


def log_metrics_to_prometheus(**context):
    """
    Экспортировать метрики дрейфа в Prometheus
    
    Использует prometheus_client для push-метрик
    """
    from prometheus_client import CollectorRegistry, Counter, Gauge, push_to_gateway
    
    task_instance = context['task_instance']
    report = task_instance.xcom_pull(
        task_ids='check_drift',
        key='drift_report'
    )
    
    # Создать реестр
    registry = CollectorRegistry()
    
    # Feature drift metrics
    for feature, metrics in report.get('feature_drift', {}).items():
        psi_metric = Gauge(
            f'flight_delay_api_feature_drift_psi_{{feature="{feature}"}}',
            'Feature drift PSI',
            registry=registry
        )
        psi_metric.set(metrics.get('psi', 0))
    
    # Performance drift
    perf_metric = Gauge(
        'flight_delay_api_auc_drop',
        'Model performance drop',
        registry=registry
    )
    perf_metric.set(report.get('performance_drift', {}).get('auc_drop', 0))
    
    # Retrain trigger
    retrain_metric = Counter(
        'flight_delay_api_retrain_triggered',
        'Retrain triggered counter',
        registry=registry
    )
    if report.get('overall_drifted'):
        retrain_metric.inc()
    
    # Push to Prometheus (если используется)
    try:
        push_to_gateway(
            'prometheus-pushgateway:9091',
            job='flight-delay-drift-check',
            registry=registry
        )
        logger.info("Metrics pushed to Prometheus")
    except Exception as e:
        logger.warning(f"Failed to push metrics: {e}")


# ============ DAG ОПРЕДЕЛЕНИЕ ============

dag = DAG(
    dag_id='flight_delay_drift_detection',
    default_args=DEFAULT_ARGS,
    description='Monitor data drift and trigger retraining',
    schedule_interval='@hourly',  # Каждый час
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=['mlops', 'monitoring', 'drift'],
)

# ============ ТАСКИ ============

start = DummyOperator(
    task_id='start',
    dag=dag,
)

check_drift = PythonOperator(
    task_id='check_drift',
    python_callable=check_drift_task,
    provide_context=True,
    dag=dag,
)

log_metrics = PythonOperator(
    task_id='log_metrics',
    python_callable=log_metrics_to_prometheus,
    provide_context=True,
    dag=dag,
)

decide = PythonOperator(
    task_id='decide_retrain',
    python_callable=decide_retrain,
    provide_context=True,
    dag=dag,
)

trigger_retrain = PythonOperator(
    task_id='trigger_retrain',
    python_callable=trigger_retrain_task,
    provide_context=True,
    dag=dag,
)

register_model = PythonOperator(
    task_id='register_model',
    python_callable=register_model_task,
    provide_context=True,
    dag=dag,
)

skip_retrain = DummyOperator(
    task_id='skip_retrain',
    dag=dag,
)

end = DummyOperator(
    task_id='end',
    trigger_rule='none_failed_min_one_success',
    dag=dag,
)

# ============ ГРАФ ЗАВИСИМОСТЕЙ ============

start >> check_drift >> log_metrics >> decide

decide >> [
    trigger_retrain >> register_model >> end,
    skip_retrain >> end,
]
```

### 4.2 Альтернатива: Cron Job вместо Airflow

Если Airflow недоступен, использовать системный cron:

Файл `scripts/drift_check_cron.sh`:

```bash
#!/bin/bash

# Скрипт для запуска проверки дрейфа каждый час через cron
# Добавить в crontab: 0 * * * * /path/to/drift_check_cron.sh

LOG_FILE="/var/log/flight-delay/drift_check.log"
PYTHON_BIN="/usr/bin/python3"
SCRIPT_PATH="/opt/flight-delay-api/src/drift_check.py"
TRAIN_SCRIPT="/opt/flight-delay-api/src/train.py"
REPORT_PATH="/opt/flight-delay-api/reports/drift_report.json"

# Запустить проверку дрейфа
echo "[$(date)] Starting drift check..." >> $LOG_FILE
$PYTHON_BIN $SCRIPT_PATH >> $LOG_FILE 2>&1

# Проверить результат
if [ $? -eq 0 ]; then
    # Прочитать отчёт и принять решение
    RETRAIN_NEEDED=$(grep -o '"overall_drifted": \(true\|false\)' $REPORT_PATH | grep -o 'true\|false')
    
    if [ "$RETRAIN_NEEDED" = "true" ]; then
        echo "[$(date)] DRIFT DETECTED - Triggering retraining..." >> $LOG_FILE
        $PYTHON_BIN $TRAIN_SCRIPT >> $LOG_FILE 2>&1
        
        if [ $? -eq 0 ]; then
            echo "[$(date)] Retraining completed successfully" >> $LOG_FILE
        else
            echo "[$(date)] Retraining failed!" >> $LOG_FILE
        fi
    else
        echo "[$(date)] No drift detected" >> $LOG_FILE
    fi
else
    echo "[$(date)] Drift check failed!" >> $LOG_FILE
fi
```

Добавить в crontab:
```bash
crontab -e
# Добавить строку:
0 * * * * /opt/flight-delay-api/scripts/drift_check_cron.sh
```

---

## ☸️ Раздел 5: Развёртывание в Kubernetes

### 5.1 Создать K8s CronJob

Файл `k8s/drift_check_cronjob.yaml`:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: flight-delay-drift-check
  namespace: default
spec:
  # Запускать каждый час в :30 минут
  schedule: "30 * * * *"
  
  jobTemplate:
    spec:
      template:
        spec:
          serviceAccountName: flight-delay-sa
          
          containers:
          - name: drift-check
            image: flight-delay-api:v1
            imagePullPolicy: IfNotPresent
            
            command:
            - /bin/sh
            - -c
            - |
              python /app/src/drift_check.py
              RETRAIN_NEEDED=$?
              
              if [ "$RETRAIN_NEEDED" -eq 1 ]; then
                echo "Triggering retraining..."
                python /app/src/train.py
              fi
            
            env:
            - name: PYTHONUNBUFFERED
              value: "1"
            - name: MODEL_PATH
              value: "/models/flight_delay_model.pkl"
            - name: DATA_PATH
              value: "/data"
            - name: REPORTS_PATH
              value: "/reports"
            
            volumeMounts:
            - name: models
              mountPath: /models
            - name: data
              mountPath: /data
            - name: reports
              mountPath: /reports
            
            resources:
              requests:
                cpu: "500m"
                memory: "512Mi"
              limits:
                cpu: "1000m"
                memory: "1Gi"
          
          volumes:
          - name: models
            persistentVolumeClaim:
              claimName: flight-delay-models-pvc
          - name: data
            persistentVolumeClaim:
              claimName: flight-delay-data-pvc
          - name: reports
            persistentVolumeClaim:
              claimName: flight-delay-reports-pvc
          
          restartPolicy: OnFailure
          backoffLimit: 3
---
# PVC для моделей
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: flight-delay-models-pvc
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 1Gi
  storageClassName: standard
---
# PVC для данных
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: flight-delay-data-pvc
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 5Gi
  storageClassName: standard
---
# PVC для отчётов
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: flight-delay-reports-pvc
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 1Gi
  storageClassName: standard
```

Развернуть:
```bash
kubectl apply -f k8s/drift_check_cronjob.yaml

# Проверить
kubectl get cronjobs
kubectl get jobs -l job-type=drift-check

# Логи
kubectl logs -l job-name=flight-delay-drift-check-<hash> -f
```

---

## 6️⃣ Раздел 6: Обновить docker-compose.yml

### 6.1 Добавить Airflow service

Файл `docker-compose.yml` (добавить к существующему):

```yaml
version: '3.8'

services:
  # ... существующие сервисы (prometheus, grafana, alertmanager) ...

  # ===== AIRFLOW =====
  airflow-postgres:
    image: postgres:14
    container_name: airflow-postgres
    environment:
      POSTGRES_USER: airflow
      POSTGRES_PASSWORD: airflow
      POSTGRES_DB: airflow
    volumes:
      - airflow_postgres_data:/var/lib/postgresql/data
    networks:
      - monitoring
    restart: unless-stopped

  airflow-webserver:
    image: apache/airflow:2.7.0-python3.11
    container_name: airflow-webserver
    depends_on:
      - airflow-postgres
    environment:
      AIRFLOW_HOME: /opt/airflow
      AIRFLOW__CORE__DAGS_FOLDER: /opt/airflow/dags
      AIRFLOW__CORE__EXECUTOR: LocalExecutor
      AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql://airflow:airflow@airflow-postgres/airflow
      AIRFLOW__CORE__LOAD_EXAMPLES: 'False'
      AIRFLOW__CORE__UNIT_TEST_MODE: 'False'
      _PIP_ADDITIONAL_REQUIREMENTS: 'apache-airflow-providers-postgres'
    ports:
      - "8080:8080"
    volumes:
      - ./dags:/opt/airflow/dags
      - ./src:/opt/airflow/src
      - ./data:/data
      - ./models:/models
      - ./reports:/reports
      - airflow_logs:/opt/airflow/logs
    command: >
      bash -c "airflow db init &&
               airflow users create --username admin --password admin --firstname Admin --lastname User --role Admin --email admin@example.com &&
               airflow webserver"
    networks:
      - monitoring
    restart: unless-stopped

  airflow-scheduler:
    image: apache/airflow:2.7.0-python3.11
    container_name: airflow-scheduler
    depends_on:
      - airflow-postgres
    environment:
      AIRFLOW_HOME: /opt/airflow
      AIRFLOW__CORE__DAGS_FOLDER: /opt/airflow/dags
      AIRFLOW__CORE__EXECUTOR: LocalExecutor
      AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql://airflow:airflow@airflow-postgres/airflow
      AIRFLOW__CORE__LOAD_EXAMPLES: 'False'
    volumes:
      - ./dags:/opt/airflow/dags
      - ./src:/opt/airflow/src
      - ./data:/data
      - ./models:/models
      - ./reports:/reports
      - airflow_logs:/opt/airflow/logs
    command: airflow scheduler
    networks:
      - monitoring
    restart: unless-stopped

  # ===== PROMETHEUS PUSHGATEWAY (для push-метрик) =====
  prometheus-pushgateway:
    image: prom/pushgateway:latest
    container_name: prometheus-pushgateway
    ports:
      - "9091:9091"
    networks:
      - monitoring
    restart: unless-stopped

volumes:
  # ... существующие volumes ...
  airflow_postgres_data:
  airflow_logs:

networks:
  monitoring:
    driver: bridge
```

Запустить:
```bash
docker-compose up -d airflow-webserver airflow-scheduler prometheus-pushgateway

# Проверить
docker-compose ps

# Открыть Airflow UI
# http://localhost:8080
# Username: admin
# Password: admin
```

---

## 📊 Раздел 7: Демонстрация дрейфа

### 7.1 Пошаговая демонстрация

```bash
# 1. Убедиться, что API работает
curl http://localhost:9696/health

# 2. Сгенерировать чистые production данные (без дрейфа)
python src/simulate_drift.py none

# 3. Запустить проверку дрейфа
python src/drift_check.py

# Посмотреть отчёт
cat reports/drift_report.json | jq .

# Ожидаемый результат:
# {
#   "overall_drifted": false,
#   "feature_drift": {
#     "duration": {"psi": 0.08, "ks": 0.05, "drifted": false},
#     ...
#   }
# }

# 4. Сгенерировать данные с ГРАДУАЛЬНЫМ дрейфом
python src/simulate_drift.py gradual

# 5. Запустить проверку дрейфа
python src/drift_check.py

# Ожидаемый результат:
# {
#   "overall_drifted": true,
#   "feature_drift": {
#     "duration": {"psi": 0.35, "ks": 0.18, "drifted": true},  # ← дрейф!
#     "departure_hour": {"psi": 0.42, "ks": 0.22, "drifted": true}
#   }
# }

# 6. Проверить, что переобучение было триггеризировано
ls -la models/
# Должен быть новый файл с временем создания

# 7. Проверить отчёт истории
cat reports/drift_history.csv

# 8. Сгенерировать ВНЕЗАПНЫЙ дрейф
python src/simulate_drift.py sudden

# 9. Запустить проверку
python src/drift_check.py

# Ожидаемый результат: очень высокие PSI значения
# {
#   "overall_drifted": true,
#   "feature_drift": {
#     "duration": {"psi": 0.87, "ks": 0.45, "drifted": true},  # ← СИЛЬНЫЙ дрейф!
#   }
# }
```

### 7.2 Демонстрация в Airflow

```bash
# 1. Открыть Airflow UI
# http://localhost:8080

# 2. Включить DAG
# Нажать на DAG → toggle ON

# 3. Запустить вручную (для тестирования)
# Click "Trigger DAG" → Execute

# 4. Смотреть прогресс
# Открыть DAG → посмотреть граф выполнения

# 5. Проверить логи
# DAG → Tasks → check_drift → Logs

# 6. Проверить XCom значения
# DAG → Tasks → check_drift → XCom

# 7. Если дрейф обнаружен:
# - trigger_retrain таск запустится
# - register_model таск обновит модель
# - Новая версия модели в моделях-директории
```

---

## 📈 Раздел 8: Мониторинг в Grafana

### 8.1 Добавить Dashboard дрейфа

Создать новый Dashboard в Grafana (http://localhost:3000):

**Panel 1: Feature Drift (PSI) за время**
```promql
flight_delay_api_feature_drift_psi
```
- Type: Time series
- Legend: `{{feature}}`

**Panel 2: Performance Drop (ROC-AUC)**
```promql
flight_delay_api_auc_drop
```
- Type: Gauge
- Threshold: 0.05 (красный)

**Panel 3: Drift History**
```sql
SELECT timestamp, overall_drifted, duration_psi, departure_hour_psi
FROM drift_history
ORDER BY timestamp DESC
LIMIT 100
```
- Type: Table

**Panel 4: Retraining Events**
```promql
increase(flight_delay_api_retrain_triggered[1h])
```
- Type: Stat

---

## 🧪 Раздел 9: Тестирование

### 9.1 Unit тесты

Файл `tests/test_drift_check.py`:

```python
import pytest
import numpy as np
import pandas as pd
from src.drift_check import calculate_psi, calculate_ks_statistic

def test_psi_no_drift():
    """PSI должен быть низким, если распределения идентичны"""
    data = np.random.normal(100, 10, 1000)
    psi = calculate_psi(data, data)
    assert psi < 0.1

def test_psi_with_drift():
    """PSI должен быть высоким при сдвиге распределения"""
    baseline = np.random.normal(100, 10, 1000)
    shifted = np.random.normal(120, 10, 1000)  # Сдвиг на 20
    psi = calculate_psi(baseline, shifted)
    assert psi > 0.25  # Значительный дрейф

def test_ks_statistic():
    """KS тест должен обнаружить различие"""
    baseline = np.random.normal(0, 1, 500)
    shifted = np.random.normal(0.5, 1, 500)
    ks = calculate_ks_statistic(baseline, shifted)
    assert ks > 0.1

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
```

Запустить:
```bash
pip install pytest
pytest tests/test_drift_check.py -v
```

---

## ✅ Раздел 10: Чек-лист оценки

| Задача | Команда/Проверка | Результат | ☑ |
|--------|------------------|-----------|---|
| **Drift Detection** | | | |
| drift_check.py работает | `python src/drift_check.py` | reports/drift_report.json создан | ☐ |
| PSI вычисляется корректно | `cat reports/drift_report.json` | PSI значения присутствуют | ☐ |
| KS тест работает | Проверка feature_drift | KS метрики > 0 | ☐ |
| Performance drift | Проверка AUC drop | Падение AUC регистрируется | ☐ |
| **Drift Simulation** | | | |
| simulate_drift.py работает | `python src/simulate_drift.py gradual` | production_recent.csv обновлен | ☐ |
| Градуальный дрейф | Запустить drift_check | `overall_drifted: true` | ☐ |
| Внезапный дрейф | `python src/simulate_drift.py sudden` | PSI > 0.5 | ☐ |
| Без дрейфа | `python src/simulate_drift.py none` | `overall_drifted: false` | ☐ |
| **Airflow Integration** | | | |
| Airflow DAG создан | http://localhost:8080 | flight_delay_drift_detection DAG | ☐ |
| DAG запускается по расписанию | Scheduler работает | DAG запускается каждый час | ☐ |
| check_drift таск работает | Logs | Drift report создается | ☐ |
| Триггеризация retrain | Нет дрейфа → skip | retrain не триггерится | ☐ |
| Триггеризация retrain | Есть дрейф → trigger | retrain запускается | ☐ |
| **Model Registry** | | | |
| Новая модель зарегистрирована | MLflow или файловая система | Версия модели увеличилась | ☐ |
| История обновлена | `ls -la models/` | Новые файлы с timestamp | ☐ |
| **Monitoring** | | | |
| Prometheus метрики | http://localhost:9090 | flight_delay_api_feature_drift_* | ☐ |
| Grafana Dashboard | http://localhost:3000 | Drift Dashboard отображает графики | ☐ |
| Alerts срабатывают | Feature drift > 0.25 | FeatureDriftDetected alert FIRING | ☐ |
| **Kubernetes (опционально)** | | | |
| CronJob создан | `kubectl get cronjobs` | flight-delay-drift-check есть | ☐ |
| CronJob запускается | `kubectl get jobs` | Новые job'ы появляются ежечасно | ☐ |
| PVC смонтированы | `kubectl describe cronjob` | volumeMounts правильно настроены | ☐ |

---

## 📚 Дополнительные ресурсы

- **Evidently AI**: https://docs.evidentlyai.com/
- **Population Stability Index**: https://en.wikipedia.org/wiki/Monitoring_and_evaluation#Stability
- **Airflow Documentation**: https://airflow.apache.org/docs/
- **Kolmogorov-Smirnov Test**: https://en.wikipedia.org/wiki/Kolmogorov%E2%80%93Smirnov_test
- **Model Drift Detection**: https://arxiv.org/abs/2310.16341

---

## 🎯 Итоговая структура проекта

```
mlops-flight-delay/
├── src/
│   ├── api.py                          # Flask API с метриками
│   ├── train.py                        # Обучение модели
│   ├── drift_check.py                  # ✨ Проверка дрейфа
│   ├── simulate_drift.py               # ✨ Симуляция дрейфа
│   └── register.py                     # Регистрация модели
│
├── dags/
│   ├── flight_delay_training_dag.py    # DAG обучения (ЛР10)
│   └── flight_delay_drift_dag.py       # ✨ DAG дрейфа
│
├── models/
│   ├── flight_delay_model.pkl          # Текущая модель
│   ├── flight_delay_model_v1.pkl       # История версий
│   ├── flight_delay_model_v2.pkl       # (после retrain)
│   └── metadata.json                   # Метаданные моделей
│
├── reports/
│   ├── drift_report.json               # ✨ Последний отчёт
│   ├── drift_history.csv               # ✨ История дрейфа
│   └── training_results.json           # Результаты обучения
│
├── data/
│   ├── train.csv                       # Baseline данные
│   ├── production_recent.csv           # Production данные
│   └── test.csv                        # Тестовый набор
│
├── prometheus/
│   ├── prometheus.yml                  # Конфиг Prometheus
│   └── alert_rules.yml                 # Alert rules (обновлены)
│
├── grafana/
│   └── provisioning/dashboards/
│       ├── flight-delay-dashboard.json # Основной dashboard
│       └── drift-dashboard.json        # ✨ Dashboard дрейфа
│
├── k8s/
│   ├── deployment.yaml
│   ├── service.yaml
│   └── drift_check_cronjob.yaml        # ✨ K8s CronJob
│
├── scripts/
│   └── drift_check_cron.sh             # ✨ Cron скрипт
│
├── tests/
│   ├── test_drift_check.py             # ✨ Unit тесты
│   └── test_integration.py
│
├── docker-compose.yml                  # Обновлено: +Airflow
├── requirements.txt                    # Обновлено: +drift deps
├── Dockerfile
├── README.md
└── .gitignore
```

---

## 🚀 Быстрый старт

```bash
# 1. Установить зависимости
pip install -r requirements.txt

# 2. Убедиться, что API работает
python src/api.py &

# 3. Сгенерировать production данные
python src/simulate_drift.py gradual

# 4. Запустить проверку дрейфа
python src/drift_check.py

# 5. Проверить отчёт
cat reports/drift_report.json | jq .

# 6. (Опционально) Запустить Airflow
docker-compose up -d airflow-webserver airflow-scheduler

# 7. Открыть Grafana и смотреть мониторинг
# http://localhost:3000/d/drift-dashboard

# 8. Генерировать нагрузку (опционально)
hey -n 5000 -c 50 "http://localhost:9696/predict" \
  -d '{"duration":50, ...}'

# 9. Смотреть алерты в Prometheus
# http://localhost:9090/alerts
```

---

**✅ Лабораторная 12 готова к выполнению!**

Основные артефакты:
- ✨ `src/drift_check.py` — проверка дрейфа через PSI/KS
- ✨ `src/simulate_drift.py` — генерация drift scenarios
- ✨ `dags/flight_delay_drift_dag.py` — Airflow DAG с триггеризацией
- ✨ `reports/drift_report.json` — отчёт о дрейфе
- ✨ `reports/drift_history.csv` — история дрейфа
- ✨ Автоматическое переобучение при обнаружении дрейфа
