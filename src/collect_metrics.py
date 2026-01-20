import json
import mlflow
import yaml
import argparse
from datetime import datetime

def collect_baseline_metrics(config, output_path="reports/baseline_metrics.json"):
    """Собираем метрики базовых моделей из MLflow"""
    
    if config['experiments']['tracking_uri']:
        mlflow.set_tracking_uri(config['experiments']['tracking_uri'])
    
    experiment_name = config['experiments']['experiment_name']
    experiment = mlflow.get_experiment_by_name(experiment_name)
    
    if experiment is None:
        print(f"Experiment {experiment_name} not found")
        return
    
    # Получаем последние запуски для каждой модели
    metrics = {}
    
    for model_type in ['random_forest', 'xgboost', 'logistic_regression']:
        runs = mlflow.search_runs(
            experiment_ids=[experiment.experiment_id],
            filter_string=f"tags.model_type = '{model_type}' and tags.model_stage != 'final'",
            order_by=["start_time DESC"],
            max_results=1
        )
        
        if not runs.empty:
            run = runs.iloc[0]
            metrics[model_type] = {
                'test_f1_score': run.get(f'metrics.test_f1_score', None),
                'test_accuracy': run.get(f'metrics.test_accuracy', None),
                'test_roc_auc': run.get(f'metrics.test_roc_auc', None),
                'run_id': run['run_id']
            }
    
    # Сохраняем метрики
    import os
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump(metrics, f, indent=2)
    
    print(f"Baseline metrics saved to {output_path}")
    return metrics

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="params.yaml", help="Config file path")
    parser.add_argument("--output", default="reports/baseline_metrics.json", help="Output metrics file")
    args = parser.parse_args()
    
    with open(args.config, 'r') as f:
        config = yaml.safe_load(f)
    
    collect_baseline_metrics(config, args.output)

if __name__ == "__main__":
    main()
