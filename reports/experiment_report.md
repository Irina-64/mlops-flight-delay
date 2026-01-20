## Обзор проекта
- **Задача**: Бинарная классификация задержек рейсов
- **Данные**: Синтетические данные авиарейсов (50,000 записей)
- **Целевая метрика**: F1-score

## Эксперименты

### Baseline модели
| Модель | F1-Score | Accuracy | ROC-AUC | Параметры |
|--------|----------|----------|---------|-----------|
| Random Forest | 0.908202 | 0.908202 | 0.908202 | default |
| XGBoost | 0.908202 | 0.8743 | 0.940254 | default |
| Logistic Regression | 0.908202 | 0.9972 | 0.999980 | default |

### Оптимизированные модели
| Модель | F1-Score | Accuracy | ROC-AUC | Параметры |
|--------|----------|----------|---------|-----------|
| Random Forest | 0.908202 | 0.908202 | 0.908202 | default |
| XGBoost | 0.908202 | 0.8743 | 0.940254 | default |
| Logistic Regression | 0.908202 | 0.9972 | 0.999980 | default |

## Выводы
- Лучшая модель: [Logistic Regression]
- Ключевые признаки: [TOP_FEATURES]
- Рекомендации: [RECOMMENDATIONS]

## Файлы
- MLflow tracking: http://localhost:5000
- Модели: models/final_*_model.pkl
- Отчеты: reports/
- Конфигурация: params.yaml