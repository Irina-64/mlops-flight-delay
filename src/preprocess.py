import pandas as pd
import numpy as np
import os

RAW_PATH = 'data/raw/flights_sample.csv'
PROCESSED_PATH = 'data/processed/processed.csv'

os.makedirs(os.path.dirname(PROCESSED_PATH), exist_ok=True)

def preprocess():
    df = pd.read_csv(RAW_PATH)

    # Заполнение NaN и преобразование типов
    df['delay'] = df['delay'].fillna(0).astype(int)
    df['price'] = df['price'].astype(int)
    df['departure_time'] = pd.to_datetime(df['departure_time'])
    df['arrival_time'] = pd.to_datetime(df['arrival_time'])

    # Признак: день недели
    df['day_of_week'] = df['departure_time'].dt.dayofweek

    # Признак: выходной
    df['is_weekend'] = df['day_of_week'].isin([5, 6]).astype(int)

    # Признак: бакетизация времени вылета
    def hour_bucket(hour):
        if 0 <= hour < 6:
            return 'night'
        elif 6 <= hour < 12:
            return 'morning'
        elif 12 <= hour < 18:
            return 'day'
        else:
            return 'evening'
    df['departure_hour_bucket'] = df['departure_time'].dt.hour.apply(hour_bucket)

    # Сохраняем результат
    df.to_csv(PROCESSED_PATH, index=False)

if __name__ == '__main__':
    preprocess()
