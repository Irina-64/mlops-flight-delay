import pandas as pd
import numpy as np
import mlflow
import mlflow.sklearn
import mlflow.xgboost
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, precision_score, recall_score, 
                           f1_score, roc_auc_score, confusion_matrix, 
                           classification_report)
import xgboost as xgb
import yaml
import argparse
import joblib
import os
from datetime import datetime
import matplotlib.pyplot as plt
import seaborn as sns

def load_config(config_path='params.yaml'):
    """Загрузка конфигурации"""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def load_data(config):
    """Загрузка подготовленных данных"""
    split_dir = config['data']['split_dir']
    
    X_train = pd.read_csv(f'{split_dir}/X_train.csv')
    X_test = pd.read_csv(f'{split_dir}/X_test.csv')
    y_train = pd.read_csv(f'{split_dir}/y_train.csv').values.ravel()
    y_test = pd.read_csv(f'{split_dir}/y_test.csv').values.ravel()
    
    return X_train, X_test, y_train, y_test

def calculate_metrics(y_true, y_pred, y_pred_proba=None):
    """Расчет метрик классификации"""
    metrics = {
        'accuracy': accuracy_score(y_true, y_pred),
        'precision': precision_score(y_true, y_pred, average='weighted'),
        'recall': recall_score(y_true, y_pred, average='weighted'),
        'f1_score': f1_score(y_true, y_pred, average='weighted')
    }
    
    if y_pred_proba is not None:
        # Для бинарной классификации
        if len(np.unique(y_true)) == 2:
            metrics['roc_auc'] = roc_auc_score(y_true, y_pred_proba[:, 1])
        else:
            metrics['roc_auc'] = roc_auc_score(y_true, y_pred_proba, multi_class='ovr')
    
    return metrics

def plot_confusion_matrix(y_true, y_pred, model_name):
    """Создание confusion matrix"""
    cm = confusion_matrix(y_true, y_pred)
    
    plt.figure(figsize=(8, 6))
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues')
    plt.title(f'Confusion Matrix - {model_name}')
    plt.ylabel('True Label')
    plt.xlabel('Predicted Label')
    
    # Сохраняем график
    plot_path = f'reports/confusion_matrix_{model_name.lower()}.png'
    os.makedirs('reports', exist_ok=True)
    plt.savefig(plot_path)
    plt.close()
    
    return plot_path

def plot_feature_importance(model, feature_names, model_name):
    """Визуализация важности признаков"""
    if hasattr(model, 'feature_importances_'):
        importances = model.feature_importances_
        indices = np.argsort(importances)[::-1][:15]  # Топ-15 признаков
        
        plt.figure(figsize=(12, 8))
        plt.title(f"Feature Importance - {model_name}")
        plt.bar(range(len(indices)), importances[indices])
        plt.xticks(range(len(indices)), [feature_names[i] for i in indices], rotation=45)
        plt.tight_layout()
        
        plot_path = f'reports/feature_importance_{model_name.lower()}.png'
        plt.savefig(plot_path)
        plt.close()
        
        return plot_path
    return None

def train_model(model_type, model_params, X_train, y_train, X_test, y_test, feature_names):
    """Обучение модели с логированием в MLflow"""
    
    with mlflow.start_run(run_name=f"{model_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"):
        # Логируем параметры
        mlflow.log_params(model_params)
        mlflow.set_tag("model_type", model_type)
        mlflow.set_tag("dataset", "flight_delays")
        
        # Создаем модель
        if model_type == "random_forest":
            model = RandomForestClassifier(**model_params)
            mlflow.sklearn.autolog()
        elif model_type == "xgboost":
            model = xgb.XGBClassifier(**model_params)
            mlflow.xgboost.autolog()
        elif model_type == "logistic_regression":
            model = LogisticRegression(**model_params)
            mlflow.sklearn.autolog()
        else:
            raise ValueError(f"Unknown model type: {model_type}")
        
        # Обучение
        print(f"Training {model_type} model...")
        model.fit(X_train, y_train)
        
        # Предсказания
        y_pred_train = model.predict(X_train)
        y_pred_test = model.predict(X_test)
        
        # Вероятности для ROC-AUC
        if hasattr(model, 'predict_proba'):
            y_pred_proba_train = model.predict_proba(X_train)
            y_pred_proba_test = model.predict_proba(X_test)
        else:
            y_pred_proba_train = None
            y_pred_proba_test = None
        
        # Рассчитываем метрики
        train_metrics = calculate_metrics(y_train, y_pred_train, y_pred_proba_train)
        test_metrics = calculate_metrics(y_test, y_pred_test, y_pred_proba_test)
        
        # Логируем метрики
        for metric, value in train_metrics.items():
            mlflow.log_metric(f"train_{metric}", value)
        
        for metric, value in test_metrics.items():
            mlflow.log_metric(f"test_{metric}", value)
        
        # Логируем overfitting индикатор
        mlflow.log_metric("overfitting_score", 
                         train_metrics['f1_score'] - test_metrics['f1_score'])
        
        # Создаем и логируем графики
        cm_path = plot_confusion_matrix(y_test, y_pred_test, model_type)
        mlflow.log_artifact(cm_path)
        
        fi_path = plot_feature_importance(model, feature_names, model_type)
        if fi_path:
            mlflow.log_artifact(fi_path)
        
        # Сохраняем модель
        model_path = f"models/{model_type}_model.pkl"
        os.makedirs("models", exist_ok=True)
        joblib.dump(model, model_path)
        
        # Логируем модель в MLflow
        if model_type in ["random_forest", "logistic_regression"]:
            mlflow.sklearn.log_model(model, "model")
        elif model_type == "xgboost":
            mlflow.xgboost.log_model(model, "model")
        
        mlflow.log_artifact(model_path)
        
        # Логируем classification report
        class_report = classification_report(y_test, y_pred_test)
        with open(f"reports/classification_report_{model_type}.txt", "w") as f:
            f.write(class_report)
        mlflow.log_artifact(f"reports/classification_report_{model_type}.txt")
        
        print(f"\n{model_type.upper()} Results:")
        print(f"Train F1: {train_metrics['f1_score']:.4f}")
        print(f"Test F1: {test_metrics['f1_score']:.4f}")
        print(f"Test Accuracy: {test_metrics['accuracy']:.4f}")
        if 'roc_auc' in test_metrics:
            print(f"Test ROC-AUC: {test_metrics['roc_auc']:.4f}")
        
        return model, test_metrics['f1_score']

def validate_data(X_train, X_test, y_train, y_test):
    """Проверка данных на утечки и проблемы"""
    print("\n" + "="*50)
    print("VALIDATING DATA")
    print("="*50)
    
    # 1. Проверка целевой переменной
    print(f"\nЦелевая переменная:")
    print(f"  Train - 0: {sum(y_train==0)}, 1: {sum(y_train==1)}")
    print(f"  Test  - 0: {sum(y_test==0)}, 1: {sum(y_test==1)}")
    
    # Проблема: все метки = 0!
    if sum(y_train == 1) == 0 or sum(y_test == 1) == 0:
        print("\n❌ КРИТИЧЕСКАЯ ПРОБЛЕМА: Нет положительных примеров (класс 1)!")
        print("   Невозможно обучать классификатор!")
        print("   Проверь создание целевой переменной в preprocess.py")
        exit(1)
    
    # 2. Удаляем только total_delay, оставляем остальные delay столбцы
    if 'total_delay' in X_train.columns:
        print(f"\nУдаляем 'total_delay' (потенциальная утечка)...")
        X_train = X_train.drop(columns=['total_delay'])
        X_test = X_test.drop(columns=['total_delay'])
    else:
        print(f"\n'total_delay' не найден в признаках")
    
    # 3. Проверяем другие столбцы с delay
    delay_cols = [col for col in X_train.columns if 'delay' in col.lower()]
    print(f"\nОстальные delay-столбцы: {delay_cols}")
    
    # 4. Проверка корреляций
    correlations = X_train.corrwith(pd.Series(y_train))
    high_corr = correlations.abs().nlargest(5)
    print(f"\nТоп-5 корреляций с целевой:")
    for col, corr in high_corr.items():
        print(f"  {col}: {corr:.4f}")
    
    return X_train, X_test

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="params.yaml", help="Config file path")
    parser.add_argument("--model", help="Specific model to train (random_forest, xgboost, logistic_regression)")
    args = parser.parse_args()
    
    # Загружаем конфигурацию
    config = load_config(args.config)
    
    # Настраиваем MLflow
    if config['experiments']['tracking_uri']:
        mlflow.set_tracking_uri(config['experiments']['tracking_uri'])
    
    experiment_name = config['experiments']['experiment_name']
    experiment = mlflow.get_experiment_by_name(experiment_name)
    if experiment is None:
        experiment_id = mlflow.create_experiment(experiment_name)
    else:
        experiment_id = experiment.experiment_id
    
    mlflow.set_experiment(experiment_name)
    
    # Загружаем данные
    print("Loading data...")
    X_train, X_test, y_train, y_test = load_data(config)
    X_train, X_test = validate_data(X_train, X_test, y_train, y_test)

    # Жесткое преобразование в int
    y_train = np.array(y_train).astype(int)
    y_test = np.array(y_test).astype(int)

    # Проверка
    print(f"y_train values: {np.unique(y_train, return_counts=True)}")
    print(f"y_test values: {np.unique(y_test, return_counts=True)}")

    # Если есть значения кроме 0 и 1
    if len(np.unique(y_train)) > 2:
        print(f"WARNING: More than 2 classes detected: {np.unique(y_train)}")
    feature_names = X_train.columns.tolist()
    
    print(f"Train set shape: {X_train.shape}")
    print(f"Test set shape: {X_test.shape}")
    print(f"Target distribution: {np.bincount(y_train.astype(int))}")
    
    # Обучаем модели
    results = {}
    models_to_train = [args.model] if args.model else config['models'].keys()
    
    for model_type in models_to_train:
        if model_type not in config['models']:
            print(f"Warning: {model_type} not found in config")
            continue
        
        model_params = config['models'][model_type]
        
        # Берем первые значения из списков параметров для базового обучения
        base_params = {}
        for param, value in model_params.items():
            if isinstance(value, list):
                base_params[param] = value[0]
            else:
                base_params[param] = value
        
        model, score = train_model(
            model_type, base_params, 
            X_train, y_train, X_test, y_test, feature_names
        )
        results[model_type] = score
    
    # Выводим сравнение результатов
    print("\n" + "="*50)
    print("COMPARISON OF MODELS:")
    print("="*50)
    for model_type, score in sorted(results.items(), key=lambda x: x[1], reverse=True):
        print(f"{model_type:20}: {score:.4f}")

if __name__ == "__main__":
    main()
