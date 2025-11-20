# ЛР9: Feature Store (Feast) — Оффлайн материализация и обучение
## Пошаговое описание для проекта mlops-flight-delay

---

## Часть 1: Установка и инициализация Feast

### Шаг 1.1 — Установка Feast

```bash
# Установите Feast
pip install feast==0.36.0
pip install feast[postgres]==0.36.0
pip install psycopg2-binary

# Или добавьте в requirements.txt
echo "feast[postgres]==0.36.0" >> requirements.txt
echo "psycopg2-binary>=2.9.0" >> requirements.txt

# Установите зависимости
pip install -r requirements.txt

# Проверьте установку
feast version
```

### Шаг 1.2 — Инициализируйте Feast проект

```bash
# Создайте Feast проект
feast init -t local flight_delay_feature_store

# Структура будет такой:
# flight_delay_feature_store/
# ├── feature_store.yaml      # Конфигурация
# ├── features/
# │   └── example_repo.py     # Определение фич
# └── data/
#     └── example_data.parquet
```

### Шаг 1.3 — Обновите структуру проекта

```bash
# Интегрируйте Feast в mlops-flight-delay
mkdir -p feature_store/features
mkdir -p feature_store/data
touch feature_store/__init__.py
touch feature_store/features/__init__.py

# Новая структура проекта:
# mlops-flight-delay/
# ├── feature_store/           # ← Feast Feature Store
# │   ├── feature_store.yaml
# │   ├── features/
# │   │   ├── flight_features.py
# │   │   └── weather_features.py
# │   └── data/
# ├── dags/
# ├── src/
# ├── data/
# ├── models/
# ├── reports/
# ├── tests/
# └── requirements.txt
```

---

## Часть 2: Определение источников данных и фич

### Шаг 2.1 — Создайте конфиг Feast

**Файл:** `feature_store/feature_store.yaml`

```yaml
project: flight_delay_features
registry: data/registry.db
provider: local
online_store:
  type: sqlite
  path: data/online_store.db
offline_store:
  type: file
entity_key_serialization_version: 2
```

### Шаг 2.2 — Определите сущности (Entities)

**Файл:** `feature_store/features/entities.py`

```python
from feast import Entity, ValueType

# Определяем основные сущности для нашего Feature Store

flight_entity = Entity(
    name="flight_id",
    value_type=ValueType.STRING,
    description="Уникальный идентификатор рейса"
)

carrier_entity = Entity(
    name="carrier",
    value_type=ValueType.STRING,
    description="Авиакомпания (carrier code)"
)

airport_entity = Entity(
    name="airport",
    value_type=ValueType.STRING,
    description="Аэропорт вылета"
)

date_entity = Entity(
    name="date",
    value_type=ValueType.STRING,
    description="Дата рейса"
)
```

### Шаг 2.3 — Определите источники данных (Data Sources)

**Файл:** `feature_store/features/data_sources.py`

```python
from feast import FileSource, ParquetSource
from datetime import timedelta

# Источник для фич по рейсам
flight_parquet_source = ParquetSource(
    path="data/processed/flights_features.parquet",
    event_timestamp_column="event_timestamp",
    created_timestamp_column="created_timestamp",
)

# Источник для фич по авиакомпаниям
carrier_parquet_source = ParquetSource(
    path="data/processed/carrier_features.parquet",
    event_timestamp_column="event_timestamp",
    created_timestamp_column="created_timestamp",
)

# Источник для фич по погоде
weather_parquet_source = ParquetSource(
    path="data/processed/weather_features.parquet",
    event_timestamp_column="event_timestamp",
    created_timestamp_column="created_timestamp",
)
```

### Шаг 2.4 — Определите Feature Views (фичи)

**Файл:** `feature_store/features/flight_features.py`

```python
from feast import FeatureView, Feature, ValueType
from datetime import timedelta
from feature_store.features.entities import flight_entity, carrier_entity
from feature_store.features.data_sources import flight_parquet_source, carrier_parquet_source

# ============ FLIGHT FEATURES ============

flight_features_view = FeatureView(
    name="flight_features",
    entities=[flight_entity],
    features=[
        Feature(name="dep_hour", dtype=ValueType.INT32),
        Feature(name="distance", dtype=ValueType.FLOAT),
        Feature(name="month", dtype=ValueType.INT32),
        Feature(name="day_of_week", dtype=ValueType.INT32),
    ],
    source=flight_parquet_source,
    ttl=timedelta(days=30),  # Time To Live - как долго хранить
    tags={
        "team": "ml",
        "source": "raw_flights",
        "version": "v1"
    }
)

# ============ CARRIER FEATURES ============

carrier_features_view = FeatureView(
    name="carrier_features",
    entities=[carrier_entity],
    features=[
        Feature(name="avg_delay", dtype=ValueType.FLOAT),
        Feature(name="on_time_pct", dtype=ValueType.FLOAT),
        Feature(name="flights_count", dtype=ValueType.INT32),
    ],
    source=carrier_parquet_source,
    ttl=timedelta(days=60),
    tags={
        "team": "ml",
        "source": "aggregated_data",
        "version": "v1"
    }
)
```

### Шаг 2.5 — Определите Weather Features

**Файл:** `feature_store/features/weather_features.py`

```python
from feast import FeatureView, Feature, ValueType
from datetime import timedelta
from feature_store.features.entities import airport_entity, date_entity
from feature_store.features.data_sources import weather_parquet_source

# ============ WEATHER FEATURES ============

weather_features_view = FeatureView(
    name="weather_features",
    entities=[airport_entity, date_entity],
    features=[
        Feature(name="temperature", dtype=ValueType.FLOAT),
        Feature(name="precipitation", dtype=ValueType.FLOAT),
        Feature(name="wind_speed", dtype=ValueType.FLOAT),
        Feature(name="weather_code", dtype=ValueType.INT32),
    ],
    source=weather_parquet_source,
    ttl=timedelta(days=90),
    tags={
        "team": "ml",
        "source": "weather_api",
        "version": "v1"
    }
)
```

---

## Часть 3: Подготовка данных для Feature Store

### Шаг 3.1 — Создайте скрипт подготовки фич

**Файл:** `src/prepare_features_for_feast.py`

```python
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os

def prepare_flight_features():
    """Подготавливает фичи для рейсов"""
    
    print("Подготавливаем flight features...")
    
    # Загружаем сырые данные
    df = pd.read_csv('data/raw/flights.csv')
    
    # Добавляем временные колонки для Feast
    df['event_timestamp'] = pd.to_datetime(df['date'])
    df['created_timestamp'] = datetime.now()
    
    # Создаем фичи
    features_df = df[[
        'flight_id',  # Entity key
        'dep_hour',
        'distance',
        'month',
        'day_of_week',
        'event_timestamp',
        'created_timestamp'
    ]].copy()
    
    # Преобразуем типы
    features_df['dep_hour'] = features_df['dep_hour'].astype('int32')
    features_df['distance'] = features_df['distance'].astype('float32')
    features_df['month'] = features_df['month'].astype('int32')
    features_df['day_of_week'] = features_df['day_of_week'].astype('int32')
    
    # Сохраняем в parquet
    os.makedirs('data/processed', exist_ok=True)
    features_df.to_parquet('data/processed/flights_features.parquet', index=False)
    
    print(f"✓ Flight features сохранены: {features_df.shape}")
    return features_df

def prepare_carrier_features():
    """Подготавливает агрегированные фичи по авиакомпаниям"""
    
    print("Подготавливаем carrier features...")
    
    df = pd.read_csv('data/raw/flights.csv')
    
    # Агрегируем по carrier
    carrier_stats = df.groupby('carrier').agg({
        'dep_delay': ['mean', 'count'],
        'is_on_time': 'mean'  # % рейсов вовремя
    }).reset_index()
    
    carrier_stats.columns = ['carrier', 'avg_delay', 'flights_count', 'on_time_pct']
    
    # Добавляем временные колонки
    carrier_stats['event_timestamp'] = datetime.now()
    carrier_stats['created_timestamp'] = datetime.now()
    
    # Преобразуем типы
    carrier_stats['avg_delay'] = carrier_stats['avg_delay'].astype('float32')
    carrier_stats['on_time_pct'] = carrier_stats['on_time_pct'].astype('float32')
    carrier_stats['flights_count'] = carrier_stats['flights_count'].astype('int32')
    
    # Сохраняем
    carrier_stats.to_parquet('data/processed/carrier_features.parquet', index=False)
    
    print(f"✓ Carrier features сохранены: {carrier_stats.shape}")
    return carrier_stats

def prepare_weather_features():
    """Подготавливает фичи по погоде"""
    
    print("Подготавливаем weather features...")
    
    # Если нет отдельного файла погоды, создаем synthetic
    dates = pd.date_range('2024-01-01', periods=365, freq='D')
    airports = ['ATL', 'LAX', 'ORD', 'DFW', 'JFK']
    
    records = []
    for date in dates:
        for airport in airports:
            records.append({
                'airport': airport,
                'date': date.strftime('%Y-%m-%d'),
                'temperature': np.random.uniform(-10, 35),
                'precipitation': np.random.uniform(0, 5),
                'wind_speed': np.random.uniform(0, 30),
                'weather_code': np.random.randint(0, 10),
                'event_timestamp': date,
                'created_timestamp': datetime.now()
            })
    
    weather_df = pd.DataFrame(records)
    
    # Преобразуем типы
    weather_df['temperature'] = weather_df['temperature'].astype('float32')
    weather_df['precipitation'] = weather_df['precipitation'].astype('float32')
    weather_df['wind_speed'] = weather_df['wind_speed'].astype('float32')
    weather_df['weather_code'] = weather_df['weather_code'].astype('int32')
    
    # Сохраняем
    weather_df.to_parquet('data/processed/weather_features.parquet', index=False)
    
    print(f"✓ Weather features сохранены: {weather_df.shape}")
    return weather_df

if __name__ == "__main__":
    print("=" * 50)
    print("Подготавливаем данные для Feast Feature Store")
    print("=" * 50)
    
    prepare_flight_features()
    prepare_carrier_features()
    prepare_weather_features()
    
    print("=" * 50)
    print("✓ Все фичи подготовлены!")
    print("=" * 50)
```

### Шаг 3.2 — Запустите подготовку фич

```bash
python src/prepare_features_for_feast.py
```

---

## Часть 4: Регистрация и материализация фич

### Шаг 4.1 — Создайте скрипт регистрации Feature Views

**Файл:** `feature_store/register_features.py`

```python
from feast import FeatureStore
from feature_store.features.flight_features import flight_features_view, carrier_features_view
from feature_store.features.weather_features import weather_features_view
from feature_store.features.entities import (
    flight_entity, carrier_entity, airport_entity, date_entity
)

def register_features():
    """Регистрирует все Feature Views в Feature Store"""
    
    print("Регистрируем Feature Views...")
    
    # Инициализируем Feature Store
    fs = FeatureStore(repo_path="feature_store")
    
    # Регистрируем сущности
    print("  Сущности:")
    print(f"    - {flight_entity.name}")
    print(f"    - {carrier_entity.name}")
    print(f"    - {airport_entity.name}")
    print(f"    - {date_entity.name}")
    
    # Регистрируем Feature Views
    print("  Feature Views:")
    print(f"    - {flight_features_view.name}")
    print(f"    - {carrier_features_view.name}")
    print(f"    - {weather_features_view.name}")
    
    # Применяем изменения
    fs.apply([
        flight_entity, carrier_entity, airport_entity, date_entity,
        flight_features_view, carrier_features_view, weather_features_view
    ])
    
    print("✓ Все Feature Views зарегистрированы!")
    
    # Показываем список
    print("\nЗарегистрированные фичи:")
    features_list = fs.list_feature_views()
    for feature_view in features_list:
        print(f"  - {feature_view.name}: {[f.name for f in feature_view.features]}")

if __name__ == "__main__":
    register_features()
```

### Шаг 4.2 — Запустите регистрацию

```bash
cd feature_store
python register_features.py
```

### Шаг 4.3 — Создайте скрипт материализации

**Файл:** `feature_store/materialize_features.py`

```python
from feast import FeatureStore
from datetime import datetime, timedelta

def materialize_features():
    """Материализует фичи (сохраняет их в оффлайн и онлайн store)"""
    
    print("=" * 50)
    print("Материализуем фичи...")
    print("=" * 50)
    
    # Инициализируем Feature Store
    fs = FeatureStore(repo_path="feature_store")
    
    # Определяем период
    start_date = datetime.now() - timedelta(days=30)
    end_date = datetime.now()
    
    print(f"Период: {start_date} -> {end_date}")
    
    try:
        # Материализуем фичи
        fs.materialize(
            start_date=start_date,
            end_date=end_date,
            feature_views=[
                "flight_features",
                "carrier_features",
                "weather_features"
            ]
        )
        
        print("✓ Фичи материализованы успешно!")
        
    except Exception as e:
        print(f"❌ Ошибка материализации: {str(e)}")
        raise

if __name__ == "__main__":
    materialize_features()
```

### Шаг 4.4 — Запустите материализацию

```bash
cd feature_store
python materialize_features.py

# Или с помощью Feast CLI
cd feature_store
feast materialize 2025-01-01 2025-11-20
```

---

## Часть 5: Использование фич в обучении модели

### Шаг 5.1 — Создайте скрипт для получения фич

**Файл:** `src/get_training_data.py`

```python
from feast import FeatureStore
import pandas as pd
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class FeatureStoreClient:
    """Клиент для работы с Feast Feature Store"""
    
    def __init__(self, repo_path="feature_store"):
        self.fs = FeatureStore(repo_path=repo_path)
        self.repo_path = repo_path
    
    def get_historical_features(self, entity_df, features_list, start_date, end_date):
        """
        Получает исторические фичи из Feature Store
        
        Args:
            entity_df: DataFrame с entity keys
            features_list: список фичей для получения
            start_date: начальная дата
            end_date: конечная дата
        
        Returns:
            DataFrame с фичами
        """
        print(f"Получаем исторические фичи...")
        print(f"  Фичи: {features_list}")
        print(f"  Период: {start_date} - {end_date}")
        print(f"  Размер entity_df: {entity_df.shape}")
        
        try:
            # Получаем фичи из Feature Store
            feature_matrix = self.fs.get_historical_features(
                entity_df=entity_df,
                features=features_list,
                full_table_query=False
            ).to_df()
            
            print(f"✓ Получено {feature_matrix.shape[1]} фич, {feature_matrix.shape[0]} строк")
            return feature_matrix
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения фич: {str(e)}")
            raise
    
    def get_online_features(self, entity_keys, features_list):
        """
        Получает онлайн фичи (реал-тайм) из Feature Store
        
        Args:
            entity_keys: словарь с entity keys
            features_list: список фичей
        
        Returns:
            словарь с фичами
        """
        print(f"Получаем онлайн фичи...")
        
        try:
            features = self.fs.get_online_features(
                entity_rows=[entity_keys],
                features=features_list
            )
            
            return features.to_dict()
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения онлайн фич: {str(e)}")
            raise
    
    def list_all_features(self):
        """Показывает список всех доступных фич"""
        
        print("Доступные Feature Views:")
        
        for feature_view in self.fs.list_feature_views():
            print(f"\n  {feature_view.name}:")
            print(f"    Entities: {[e.name for e in feature_view.entities]}")
            print(f"    Features:")
            for feature in feature_view.features:
                print(f"      - {feature.name} ({feature.dtype})")

def prepare_training_data():
    """Подготавливает тренировочные данные используя Feature Store"""
    
    print("=" * 50)
    print("Подготавливаем тренировочные данные")
    print("=" * 50)
    
    # Инициализируем клиент
    client = FeatureStoreClient()
    
    # Показываем доступные фичи
    client.list_all_features()
    
    # Загружаем исходные данные (с flight_id и dates)
    df = pd.read_csv('data/raw/flights.csv')
    
    # Подготавливаем entity_df (нужны для получения фич)
    entity_df = df[['flight_id']].copy()
    entity_df['date'] = df['date']
    
    # Список фич которые нам нужны
    features = [
        "flight_features:dep_hour",
        "flight_features:distance",
        "flight_features:month",
        "flight_features:day_of_week",
        "carrier_features:avg_delay",
        "carrier_features:on_time_pct",
        "carrier_features:flights_count",
    ]
    
    # Получаем фичи из Feature Store
    try:
        feature_matrix = client.get_historical_features(
            entity_df=entity_df,
            features_list=features,
            start_date=df['date'].min(),
            end_date=df['date'].max()
        )
        
        # Объединяем с target переменной
        training_data = feature_matrix.copy()
        training_data['dep_delay'] = df['dep_delay'].values
        
        # Сохраняем
        training_data.to_csv('data/processed/training_data_from_feast.csv', index=False)
        
        print(f"\n✓ Тренировочные данные подготовлены")
        print(f"  Размер: {training_data.shape}")
        print(f"  Колонки: {list(training_data.columns)}")
        
        return training_data
        
    except Exception as e:
        logger.error(f"❌ Ошибка подготовки данных: {str(e)}")
        raise

if __name__ == "__main__":
    training_data = prepare_training_data()
    print("\nПервые 5 строк:")
    print(training_data.head())
```

### Шаг 5.2 — Обновите скрипт обучения модели

**Файл:** `src/train.py` (обновленная версия)

```python
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score
import joblib
import logging
from src.get_training_data import prepare_training_data

logger = logging.getLogger(__name__)

def train_model_with_feast():
    """Обучает модель используя фичи из Feast Feature Store"""
    
    print("=" * 50)
    print("Обучение модели с использованием Feast")
    print("=" * 50)
    
    # 1. Получаем тренировочные данные из Feast
    print("\n1. Получаем данные из Feature Store...")
    training_data = prepare_training_data()
    
    # 2. Подготавливаем X и y
    print("2. Подготавливаем данные...")
    X = training_data.drop('dep_delay', axis=1)
    y = training_data['dep_delay']
    
    print(f"   X shape: {X.shape}")
    print(f"   y shape: {y.shape}")
    print(f"   Фичи: {list(X.columns)}")
    
    # 3. Split на train/test
    print("3. Разбиваем на train/test...")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )
    
    print(f"   Train: {X_train.shape}, Test: {X_test.shape}")
    
    # 4. Тренируем модель
    print("4. Обучаем модель...")
    model = RandomForestClassifier(
        n_estimators=100,
        max_depth=10,
        random_state=42,
        n_jobs=-1
    )
    
    model.fit(X_train, y_train)
    
    # 5. Оцениваем
    print("5. Оцениваем качество...")
    train_pred = model.predict(X_train)
    test_pred = model.predict(X_test)
    
    train_acc = accuracy_score(y_train, train_pred)
    test_acc = accuracy_score(y_test, test_pred)
    test_f1 = f1_score(y_test, test_pred)
    
    print(f"   Train Accuracy: {train_acc:.3f}")
    print(f"   Test Accuracy: {test_acc:.3f}")
    print(f"   Test F1: {test_f1:.3f}")
    
    # 6. Feature importance
    print("6. Feature Importance:")
    feature_importance = pd.DataFrame({
        'feature': X.columns,
        'importance': model.feature_importances_
    }).sort_values('importance', ascending=False)
    
    print(feature_importance.to_string(index=False))
    
    # 7. Сохраняем модель
    print("7. Сохраняем модель...")
    joblib.dump(model, 'models/flight_delay_model_v1.pkl')
    
    # Сохраняем метрики
    metrics = {
        'train_accuracy': float(train_acc),
        'test_accuracy': float(test_acc),
        'test_f1': float(test_f1),
        'n_features': len(X.columns),
        'feature_names': list(X.columns)
    }
    
    import json
    with open('reports/model_metrics_feast.json', 'w') as f:
        json.dump(metrics, f, indent=2)
    
    print("\n✓ Модель успешно обучена и сохранена!")
    print(f"  Модель: models/flight_delay_model_v1.pkl")
    print(f"  Метрики: reports/model_metrics_feast.json")
    
    return model, metrics

if __name__ == "__main__":
    model, metrics = train_model_with_feast()
```

### Шаг 5.3 — Запустите обучение

```bash
# Сначала подготовьте фичи
python src/prepare_features_for_feast.py

# Затем обучите модель
python src/train.py
```

---

## Часть 6: Использование фич в inference

### Шаг 6.1 — Создайте скрипт для онлайн predictions

**Файл:** `src/predict_with_feast.py`

```python
from src.get_training_data import FeatureStoreClient
import joblib
import pandas as pd
from datetime import datetime

def predict_with_feast(flight_id, carrier, dep_hour, distance):
    """
    Делает prediction используя фичи из Feast
    
    Args:
        flight_id: ID рейса
        carrier: код авиакомпании
        dep_hour: час вылета
        distance: расстояние
    
    Returns:
        prediction, probabilities
    """
    
    print("=" * 50)
    print("Prediction с использованием Feast Feature Store")
    print("=" * 50)
    
    # 1. Инициализируем Feature Store клиент
    client = FeatureStoreClient()
    
    # 2. Подготавливаем entity row
    entity_row = {
        "flight_id": flight_id,
        "carrier": carrier,
        "date": datetime.now().strftime("%Y-%m-%d")
    }
    
    print(f"\nEntity: {entity_row}")
    
    # 3. Получаем онлайн фичи
    print("\nПолучаем онлайн фичи...")
    try:
        features_dict = client.get_online_features(
            entity_keys=entity_row,
            features_list=[
                "flight_features:dep_hour",
                "flight_features:distance",
                "carrier_features:avg_delay",
                "carrier_features:on_time_pct",
            ]
        )
        
        print(f"✓ Фичи получены:")
        for key, value in features_dict.items():
            print(f"  {key}: {value}")
        
    except Exception as e:
        print(f"❌ Ошибка получения фич: {str(e)}")
        # Fallback к default values
        features_dict = {
            "flight_features:dep_hour": [dep_hour],
            "flight_features:distance": [distance],
            "carrier_features:avg_delay": [5.0],
            "carrier_features:on_time_pct": [0.8],
        }
    
    # 4. Подготавливаем фичи для модели
    features_for_model = pd.DataFrame({
        'dep_hour': features_dict.get("flight_features:dep_hour", [dep_hour]),
        'distance': features_dict.get("flight_features:distance", [distance]),
        'avg_delay': features_dict.get("carrier_features:avg_delay", [5.0]),
        'on_time_pct': features_dict.get("carrier_features:on_time_pct", [0.8]),
    })
    
    # 5. Загружаем модель
    print("\nЗагружаем модель...")
    model = joblib.load('models/flight_delay_model_v1.pkl')
    
    # 6. Делаем prediction
    print("Делаем prediction...")
    prediction = model.predict(features_for_model)[0]
    probability = model.predict_proba(features_for_model)[0]
    
    print(f"\n✓ Prediction результат:")
    print(f"  Delay predicted: {bool(prediction)}")
    print(f"  Probability (no delay): {probability[0]:.2%}")
    print(f"  Probability (delay): {probability[1]:.2%}")
    
    return prediction, probability

if __name__ == "__main__":
    # Пример использования
    prediction, prob = predict_with_feast(
        flight_id="AA123",
        carrier="AA",
        dep_hour=9,
        distance=500
    )
```

---

## Часть 7: Интеграция с Airflow DAG

### Шаг 7.1 — Создайте DAG для Feature Store

**Файл:** `dags/feast_feature_pipeline.py`

```python
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator

default_args = {
    'owner': 'ml-team',
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
    'start_date': datetime(2025, 1, 1),
}

dag = DAG(
    dag_id='feast_feature_pipeline',
    default_args=default_args,
    description='Feast Feature Store pipeline',
    schedule_interval='@daily',
    catchup=False,
    tags=['feast', 'features'],
)

def prepare_features(**context):
    """Подготавливает фичи для Feast"""
    print("Подготавливаем фичи...")
    from src.prepare_features_for_feast import (
        prepare_flight_features,
        prepare_carrier_features,
        prepare_weather_features
    )
    
    prepare_flight_features()
    prepare_carrier_features()
    prepare_weather_features()

def register_features(**context):
    """Регистрирует Feature Views"""
    print("Регистрируем Feature Views...")
    from feature_store.register_features import register_features
    register_features()

def materialize_features(**context):
    """Материализует фичи"""
    print("Материализуем фичи...")
    from feature_store.materialize_features import materialize_features
    materialize_features()

# Таски
task_prepare = PythonOperator(
    task_id='prepare_features',
    python_callable=prepare_features,
    dag=dag,
)

task_register = PythonOperator(
    task_id='register_features',
    python_callable=register_features,
    dag=dag,
)

task_materialize = PythonOperator(
    task_id='materialize_features',
    python_callable=materialize_features,
    dag=dag,
)

task_train = BashOperator(
    task_id='train_model',
    bash_command='cd {{ var.value.project_root }} && python src/train.py',
    dag=dag,
)

# Зависимости
task_prepare >> task_register >> task_materialize >> task_train
```

---

## Часть 8: Управление Feature Store

### Шаг 8.1 — CLI команды Feast

```bash
# Инициализировать проект
feast init my_feature_store

# Регистрировать фичи
cd feature_store
feast apply

# Материализировать фичи
feast materialize 2025-01-01 2025-11-20

# Материализировать конкретные feature views
feast materialize 2025-01-01 2025-11-20 --feature-views flight_features

# Просмотреть все фичи
feast feature-views list

# Информация о фиче
feast feature-views describe flight_features

# Просмотреть entities
feast entities list

# Просмотреть data sources
feast data-sources list

# Проверить registry
feast registry-dump

# Запустить validation
feast validation run
```

---

## Часть 9: Контрольный список завершения ЛР9

**Базовые требования:**
- [ ] Feast установлен и инициализирован
- [ ] Создан feature_store/ директорий
- [ ] Определены entities (flight_id, carrier, airport, date)
- [ ] Определены data sources для фич
- [ ] Созданы Feature Views (flight_features, carrier_features, weather_features)
- [ ] Фичи зарегистрированы в Feature Store (feast apply)
- [ ] Данные материализованы (feast materialize)

**Подготовка данных:**
- [ ] Создан скрипт prepare_features_for_feast.py
- [ ] Создан скрипт get_training_data.py с FeatureStoreClient
- [ ] Данные сохранены в правильном формате (parquet)
- [ ] Проверены типы данных

**Обучение модели:**
- [ ] Модель обучена используя фичи из Feast
- [ ] Сравнены результаты (с Feast vs без Feast)
- [ ] Сохранены метрики обучения
- [ ] Feature importance проанализирован

**Inference и Production:**
- [ ] Создан скрипт predict_with_feast.py для онлайн predictions
- [ ] Онлайн store настроен (SQLite)
- [ ] Тестированы онлайн predictions
- [ ] Обработаны error cases

**Интеграция:**
- [ ] DAG для Feature Store создан в Airflow
- [ ] Pipeline запускается успешно
- [ ] Логирование добавлено
- [ ] Documentation обновлена

**Advanced (опционально):**
- [ ] PostgreSQL вместо SQLite используется
- [ ] Redis онлайн store настроен
- [ ] Feature versioning реализован
- [ ] Data quality checks добавлены

---

## Шпаргалка команд Feast

```bash
# Установка
pip install feast[postgres]

# Инициализация
feast init feature_store

# Применение изменений
cd feature_store
feast apply

# Материализация
feast materialize 2025-01-01 2025-11-20
feast materialize-incremental 2025-11-20

# Просмотр
feast feature-views list
feast entities list
feast data-sources list

# Registry
feast registry-dump
feast registry-list-commits

# Управление
feast teardown
feast ui  # Запустить UI
```

---

## Полезные ссылки

- **Feast Documentation:** https://docs.feast.dev/
- **Feast GitHub:** https://github.com/feast-dev/feast
- **Feature Store Best Practices:** https://docs.feast.dev/guides/best-practices
- **Getting Started:** https://docs.feast.dev/getting-started/quickstart
- **API Reference:** https://api.docs.feast.dev/

---

**Версия: 1.0 | Ноябрь 2025**
