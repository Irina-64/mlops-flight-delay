import mlflow
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import yaml
import argparse

def load_config(config_path='params.yaml'):
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def analyze_experiments(config):
    """Анализ всех экспериментов"""
    
    if config['experiments']['tracking_uri']:
        mlflow.set_tracking_uri(config['experiments']['tracking_uri'])
    
    experiment_name = config['experiments']['experiment_name']
    experiment = mlflow.get_experiment_by_name(experiment_name)
    
    if experiment is None:
        print(f"Experiment {experiment_name} not found")
        return
    
    # Получаем все запуски
    runs = mlflow.search_runs(experiment_ids=[experiment.experiment_id])
    
    if runs.empty:
        print("No runs found")
        return
    
    print(f"Found {len(runs)} runs")
    
    # Фильтруем нужные колонки
    metric_cols = [col for col in runs.columns if col.startswith('metrics.')]
    param_cols = [col for col in runs.columns if col.startswith('params.')]
    tag_cols = [col for col in runs.columns if col.startswith('tags.')]
    
    # Создаем сводную таблицу
    summary_df = runs[['run_id', 'status', 'start_time'] + metric_cols + param_cols + tag_cols].copy()
    
    # Группируем по типу модели
    model_summary = []
    for model_type in ['random_forest', 'xgboost', 'logistic_regression']:
        model_runs = runs[runs['tags.model_type'] == model_type]
        if not model_runs.empty:
            best_run = model_runs.loc[model_runs['metrics.test_f1_score'].idxmax()]
            model_summary.append({
                'model_type': model_type,
                'best_f1_score': best_run['metrics.test_f1_score'],
                'best_accuracy': best_run['metrics.test_accuracy'],
                'best_roc_auc': best_run.get('metrics.test_roc_auc', None),
                'num_experiments': len(model_runs)
            })
    
    summary_df = pd.DataFrame(model_summary)
    
    # Визуализация результатов
    fig, axes = plt.subplots(2, 2, figsize=(15, 12))
    fig.suptitle('ML Experiment Analysis', fontsize=16)
    
    # 1. Сравнение моделей по F1-score
    axes[0, 0].bar(summary_df['model_type'], summary_df['best_f1_score'])
    axes[0, 0].set_title('Best F1-Score by Model Type')
    axes[0, 0].set_ylabel('F1-Score')
    axes[0, 0].tick_params(axis='x', rotation=45)
    
    # 2. Сравнение моделей по Accuracy
    axes[0, 1].bar(summary_df['model_type'], summary_df['best_accuracy'], color='orange')
    axes[0, 1].set_title('Best Accuracy by Model Type')
    axes[0, 1].set_ylabel('Accuracy')
    axes[0, 1].tick_params(axis='x', rotation=45)
    
    # 3. Количество экспериментов
    axes[1, 0].bar(summary_df['model_type'], summary_df['num_experiments'], color='green')
    axes[1, 0].set_title('Number of Experiments by Model Type')
    axes[1, 0].set_ylabel('Number of Runs')
    axes[1, 0].tick_params(axis='x', rotation=45)
    
    # 4. ROC-AUC сравнение
    roc_data = summary_df.dropna(subset=['best_roc_auc'])
    if not roc_data.empty:
        axes[1, 1].bar(roc_data['model_type'], roc_data['best_roc_auc'], color='red')
        axes[1, 1].set_title('Best ROC-AUC by Model Type')
        axes[1, 1].set_ylabel('ROC-AUC')
        axes[1, 1].tick_params(axis='x', rotation=45)
    
    plt.tight_layout()
    
    # Сохраняем график
    import os
    os.makedirs('reports', exist_ok=True)
    plt.savefig('reports/experiment_analysis.png', dpi=300, bbox_inches='tight')
    plt.show()
    
    # Печатаем сводку
    print("\n" + "="*60)
    print("EXPERIMENT SUMMARY")
    print("="*60)
    print(summary_df.to_string(index=False))
    
    return summary_df

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="params.yaml", help="Config file path")
    args = parser.parse_args()
    
    config = load_config(args.config)
    analyze_experiments(config)

if __name__ == "__main__":
    main()
