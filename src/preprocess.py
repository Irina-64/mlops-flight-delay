import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler, LabelEncoder
import joblib
import yaml
import argparse
import os

def load_config(config_path='params.yaml'):
    """Загрузка конфигурации"""
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    return config

def preprocess_flight_data(raw_path, processed_path, config):
    """Основная функция предобработки данных"""
    print(f"Загружаем данные из {raw_path}")
    df = pd.read_csv(raw_path)
    
    print(f"Исходный размер данных: {df.shape}")
    
    # 1. Очистка данных
    df = clean_data(df, config['preprocess'])
    
    # 2. Feature engineering
    df = create_features(df, config['preprocess'])
    
    # 3. Кодирование категориальных признаков
    df, encoders = encode_categorical(df, config['preprocess'])
    
    # 4. Масштабирование числовых признаков
    df, scaler = scale_numerical(df, config['preprocess'])
    
    print(f"Финальный размер данных: {df.shape}")
    
    # Сохранение обработанных данных
    os.makedirs(os.path.dirname(processed_path), exist_ok=True)
    df.to_csv(processed_path, index=False)
    
    # Сохранение препроцессоров
    joblib.dump(encoders, 'models/encoders.pkl')
    joblib.dump(scaler, 'models/scaler.pkl')
    
    return df

def clean_data(df, config):
    """Очистка данных"""
    # Удаляем дубликаты
    initial_shape = df.shape[0]
    df = df.drop_duplicates()
    print(f"Удалено дубликатов: {initial_shape - df.shape[0]}")
    
    # Обработка пропусков
    if config['handle_missing']:
        df = df.dropna(subset=['origin', 'dest', 'airline'])
        df = df.fillna(0)  # Заполняем числовые пропуски
    
    # Фильтрация выбросов
    if config['remove_outliers']:
        # Удаляем рейсы с нереалистичными задержками (>500 минут)
        df = df[df['delay_minutes'] <= 500]
        print(f"Размер после фильтрации выбросов: {df.shape}")
    
    return df

def create_features(df, config):
    """Создание новых признаков"""
    # Преобразуем время в удобный формат
    df['dep_hour'] = df['scheduled_dep_time'] // 100
    df['dep_minute'] = df['scheduled_dep_time'] % 100
    
    # Создаем признак "время дня"
    df['time_of_day'] = pd.cut(df['dep_hour'], 
                              bins=[0, 6, 12, 18, 24], 
                              labels=['night', 'morning', 'afternoon', 'evening'])
    
    # Признак выходного дня
    df['flight_date'] = pd.to_datetime(df['flight_date'])
    df['is_weekend'] = (df['flight_date'].dt.dayofweek >= 5).astype(int)
    df['month'] = df['flight_date'].dt.month
    df['day_of_week'] = df['flight_date'].dt.dayofweek
    
    # Бинарный признак "дальний рейс"
    df['is_long_distance'] = (df['distance'] > df['distance'].quantile(0.75)).astype(int)
    
    # Суммарная задержка по типам
    delay_cols = ['weather_delay', 'security_delay', 'airline_delay', 'late_aircraft_delay']
    df['total_delay'] = df[delay_cols].sum(axis=1)
    
    return df

def encode_categorical(df, config):
    """Кодирование категориальных признаков"""
    categorical_cols = ['airline', 'origin', 'dest', 'time_of_day']
    encoders = {}
    
    for col in categorical_cols:
        if col in df.columns:
            encoder = LabelEncoder()
            df[f'{col}_encoded'] = encoder.fit_transform(df[col].astype(str))
            encoders[col] = encoder
    
    return df, encoders

def scale_numerical(df, config):
    """Масштабирование числовых признаков"""
    numerical_cols = ['distance', 'dep_hour', 'month', 'day_of_week', 
                     'weather_delay', 'security_delay', 'airline_delay', 
                     'late_aircraft_delay', 'is_weekend', 'is_long_distance']
    
    scaler = StandardScaler()
    df[numerical_cols] = scaler.fit_transform(df[numerical_cols])
    
    return df, scaler

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="params.yaml", help="Config file path")
    args = parser.parse_args()
    
    config = load_config(args.config)
    
    preprocess_flight_data(
        raw_path=config['data']['raw'],
        processed_path=config['data']['processed'],
        config=config
    )