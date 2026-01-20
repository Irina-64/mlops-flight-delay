import pandas as pd
import numpy as np
import mlflow
import mlflow.sklearn
import mlflow.xgboost
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, precision_score, recall_score, 
                           f1_score, roc_auc_score, confusion_matrix)
import xgboost as xgb
import yaml
import argparse
import joblib
import os
import pickle
from datetime import datetime
import matplotlib.pyplot as plt
import seaborn as sns
import shap

def load_config(config_path='params.yaml'):
    """Загрузка конфигурации"""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def load_data(config):
    """Загрузка данных"""
    split_dir = config['data']['split_dir']
    
    X_train = pd.read_csv(f'{split_dir}/X_train.csv')
    X_test = pd.read_csv(f'{split_dir}/X_test.csv')
    y_train = pd.read_csv(f'{split_dir}/y_train.csv').values.ravel()
    y_test = pd.read_csv(f'{split_dir}/y_test.csv').values.ravel()
    
    return X_train, X_test, y_train, y_test

def load_best_params_from_mlflow(experiment_name, model_type):
    """Загрузка лучших параметров из MLflow"""
    
    experiment = mlflow.get_experiment_by_name(experiment_name)
    if experiment is None:
        print(f"Experiment {experiment_name} not found")
        return None
    
    runs = mlflow.search_runs(
        experiment_ids=[experiment.experiment_id],
        filter_string=f"tags.model_type = '{model_type}'",
        order_by=["metrics.best_cv_score DESC"],
        max_results=1
    )
    
    if runs.empty:
        print(f"No runs found for {model_type}")
        return None
    
    best_run = runs.iloc[0]
    
    # Извлекаем лучшие параметры
    best_params = {}
    for col in best_run.index:
        if col.startswith(f'params.best_'):
            param_name = col.replace(f'params.best_', '')
            param_value = best_run[col]
            
            # Конвертируем типы
            if param_name in ['n_estimators', 'max_depth', 'min_samples_split', 'max_iter']:
                if param_value == 'None':
                    best_params[param_name] = None
                else:
                    best_params[param_name] = int(float(param_value))
            elif param_name in ['learning_rate', 'C']:
                best_params[param_name] = float(param_value)
            else:
                best_params[param_name] = param_value
    
    # Добавляем фиксированные параметры
    best_params['random_state'] = 42
    if model_type == 'xgboost':
        best_params['eval_metric'] = 'logloss'
    
    print(f"Best parameters for {model_type}: {best_params}")
    return best_params

def create_shap_plots(model, X_test, model_name):
    """Создание SHAP графиков"""
    try:
        # Создаем explainer
        if hasattr(model, 'predict_proba'):
            explainer = shap.Explainer(model, X_test.sample(min(100, len(X_test))))
        else:
            explainer = shap.Explainer(model.predict, X_test.sample(min(100, len(X_test))))
        
        # Вычисляем SHAP values для подвыборки
        X_sample = X_test.sample(min(50, len(X_test)))
        shap_values = explainer(X_sample)
        
        # Summary plot
        plt.figure(figsize=(10, 8))
        if hasattr(shap_values, 'values') and shap_values.values.ndim > 2:
            shap.summary_plot(shap_values.values[:, :, 1], X_sample, show=False)
        else:
            shap.summary_plot(shap_values, X_sample, show=False)
        plt.title(f'SHAP Summary Plot - {model_name}')
        
        shap_path = f'reports/shap_summary_{model_name.lower()}.png'
        plt.savefig(shap_path, bbox_inches='tight')
        plt.close()
        
        return shap_path
        
    except Exception as e:
        print(f"Could not create SHAP plots: {e}")
        return None

def train_final_model(model_type, best_params, X_train, y_train, X_test, y_test):
    """Обучение финальной модели с лучшими параметрами"""
    
    run_name = f"final_{model_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    with mlflow.start_run(run_name=run_name):
        # Логируем параметры
        mlflow.log_params(best_params)
        mlflow.set_tag("model_type", model_type)
        mlflow.set_tag("model_stage", "final")
        mlflow.set_tag("dataset", "flight_delays")
        
        # Создаем и обучаем модель
        if model_type == "random_forest":
            model = RandomForestClassifier(**best_params)
        elif model_type == "xgboost":
            model = xgb.XGBClassifier(**best_params)
        elif model_type == "logistic_regression":
            model = LogisticRegression(**best_params)
        
        print(f"Training final {model_type} model...")
        model.fit(X_train, y_train)
        
        # Предсказания
        y_pred_train = model.predict(X_train)
        y_pred_test = model.predict(X_test)
        
        if hasattr(model, 'predict_proba'):
            y_pred_proba_test = model.predict_proba(X_test)
        
        # Метрики
        train_metrics = {
            'accuracy': accuracy_score(y_train, y_pred_train),
            'precision': precision_score(y_train, y_pred_train, average='weighted'),
            'recall': recall_score(y_train, y_pred_train, average='weighted'),
            'f1_score': f1_score(y_train, y_pred_train, average='weighted')
        }
        
        test_metrics = {
            'accuracy': accuracy_score(y_test, y_pred_test),
            'precision': precision_score(y_test, y_pred_test, average='weighted'),
            'recall': recall_score(y_test, y_pred_test, average='weighted'),
            'f1_score': f1_score(y_test, y_pred_test, average='weighted')
        }
        
        if hasattr(model, 'predict_proba'):
            test_metrics['roc_auc'] = roc_auc_score(y_test, y_pred_proba_test[:, 1])
        
        # Логируем метрики
        for metric, value in train_metrics.items():
            mlflow.log_metric(f"final_train_{metric}", value)
        
        for metric, value in test_metrics.items():
            mlflow.log_metric(f"final_test_{metric}", value)
        
        mlflow.log_metric("final_overfitting", 
                         train_metrics['f1_score'] - test_metrics['f1_score'])
        
        # Confusion Matrix
        cm = confusion_matrix(y_test, y_pred_test)
        plt.figure(figsize=(8, 6))
        sns.heatmap(cm, annot=True, fmt='d', cmap='Blues')
        plt.title(f'Final Model Confusion Matrix - {model_type}')
        plt.ylabel('True Label')
        plt.xlabel('Predicted Label')
        
        cm_path = f'reports/final_confusion_matrix_{model_type}.png'
        os.makedirs('reports', exist_ok=True)
        plt.savefig(cm_path)
        plt.close()
        mlflow.log_artifact(cm_path)
        
        # Feature Importance
        if hasattr(model, 'feature_importances_'):
            importances = model.feature_importances_
            feature_names = X_train.columns.tolist()
            indices = np.argsort(importances)[::-1][:15]
            
            plt.figure(figsize=(12, 8))
            plt.title(f"Final Model Feature Importance - {model_type}")
            plt.bar(range(len(indices)), importances[indices])
            plt.xticks(range(len(indices)), [feature_names[i] for i in indices], rotation=45)
            plt.tight_layout()
            
            fi_path = f'reports/final_feature_importance_{model_type}.png'
            plt.savefig(fi_path)
            plt.close()
            mlflow.log_artifact(fi_path)
        
        # SHAP анализ
        shap_path = create_shap_plots(model, X_test, f"final_{model_type}")
        if shap_path:
            mlflow.log_artifact(shap_path)
        
        # Сохраняем финальную модель
        final_model_path = f"models/final_{model_type}_model.pkl"
        joblib.dump(model, final_model_path)
        mlflow.log_artifact(final_model_path)
        
        # Регистрируем модель в Model Registry
        if model_type in ["random_forest", "logistic_regression"]:
            model_info = mlflow.sklearn.log_model(
                model, 
                "model",
                registered_model_name=f"FlightDelay_{model_type.title()}"
            )
        elif model_type == "xgboost":
            model_info = mlflow.xgboost.log_model(
                model, 
                "model",
                registered_model_name=f"FlightDelay_{model_type.title()}"
            )
        
        print(f"\nFinal {model_type.upper()} Results:")
        print(f"Test F1-Score: {test_metrics['f1_score']:.4f}")
        print(f"Test Accuracy: {test_metrics['accuracy']:.4f}")
        print(f"Test ROC-AUC: {test_metrics.get('roc_auc', 'N/A')}")
        
        return model, test_metrics['f1_score'], model_info.model_uri

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
    parser.add_argument("--model", required=True,
                       choices=['random_forest', 'xgboost', 'logistic_regression'],
                       help="Model to train with best parameters")
    args = parser.parse_args()
    
    config = load_config(args.config)
    
    # Setup MLflow
    if config['experiments']['tracking_uri']:
        mlflow.set_tracking_uri(config['experiments']['tracking_uri'])
    
    experiment_name = config['experiments']['experiment_name']
    mlflow.set_experiment(experiment_name)
    
    # Load data
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
    
    # Load best parameters from hyperopt experiment
    hyperopt_experiment_name = f"{experiment_name}_hyperopt"
    best_params = load_best_params_from_mlflow(hyperopt_experiment_name, args.model)
    
    if best_params is None:
        print("No optimized parameters found. Using default parameters.")
        # Fallback to config parameters
        model_config = config['models'][args.model]
        best_params = {k: v[0] if isinstance(v, list) else v 
                      for k, v in model_config.items()}
    
    # Train final model
    model, score, model_uri = train_final_model(
        args.model, best_params, X_train, y_train, X_test, y_test
    )
    
    print(f"\nFinal model training completed!")
    print(f"Model URI: {model_uri}")
    print(f"F1-Score: {score:.4f}")

if __name__ == "__main__":
    main()
