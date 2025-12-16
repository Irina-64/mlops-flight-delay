import pandas as pd
import json
import argparse
import numpy as np

def numpy_serializer(obj):
    if isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64, np.float32)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    raise TypeError(f"Type {type(obj)} not serializable")

def validate_processed_data(data_path):
    """Валидация обработанных данных"""
    df = pd.read_csv(data_path)
    
    validation_results = {}
    
    # Проверка размера данных
    validation_results['data_shape'] = df.shape
    validation_results['missing_values'] = df.isnull().sum().sum()
    
    # Проверка диапазонов
    validation_results['target_distribution'] = df['is_delayed'].value_counts().to_dict()
    
    # Проверка типов данных
    validation_results['data_types'] = df.dtypes.apply(str).to_dict()
    
    # Статистики по числовым колонкам
    numeric_cols = df.select_dtypes(include=['float64', 'int64']).columns
    validation_results['numeric_stats'] = df[numeric_cols].describe().to_dict()
    
    # Сохранение отчета
    with open('reports/data_validation.json', 'w') as f:
        json.dump(validation_results, f, indent=2, default=numpy_serializer)
    
    print("Валидация данных завершена")
    return validation_results

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, help="Path to processed data")
    args = parser.parse_args()
    
    # Создаем директорию для отчетов
    import os
    os.makedirs('reports', exist_ok=True)
    
    validate_processed_data(args.data)