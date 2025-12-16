import pandas as pd
from sklearn.model_selection import train_test_split
import yaml
import argparse
import os

def load_config(config_path='params.yaml'):
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def split_data(processed_path, config):
    """Разделение данных на train/test"""
    df = pd.read_csv(processed_path)
    
    # Определяем признаки и целевую переменную
    feature_cols = [col for col in df.columns if col not in ['is_delayed', 'delay_minutes', 'flight_date']]
    
    X = df[feature_cols]
    y = df['is_delayed']
    
    # Разделяем данные
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, 
        test_size=config['preprocess']['test_size'],
        random_state=config['preprocess']['random_state'],
        stratify=y
    )
    
    # Сохраняем разделенные данные
    os.makedirs('data/split', exist_ok=True)
    
    X_train.to_csv('data/split/X_train.csv', index=False)
    X_test.to_csv('data/split/X_test.csv', index=False)
    y_train.to_csv('data/split/y_train.csv', index=False)
    y_test.to_csv('data/split/y_test.csv', index=False)
    
    print(f"Train set: {X_train.shape}")
    print(f"Test set: {X_test.shape}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="params.yaml")
    args = parser.parse_args()
    
    config = load_config(args.config)
    split_data(config['data']['processed'], config)