import pandas as pd
import numpy as np

np.random.seed(42)
n = 100

airlines = ['Aeroflot', 'S7', 'Pobeda', 'UTair']
origins = ['DME', 'SVO', 'LED', 'KUF']
destinations = ['KZN', 'OVB', 'AER', 'VKO']

df = pd.DataFrame({
    'flight_id': np.arange(1, n+1),
    'airline': np.random.choice(airlines, n),
    'origin': np.random.choice(origins, n),
    'destination': np.random.choice(destinations, n),
    'departure_time': pd.date_range('2025-10-01', periods=n, freq='3h').astype(str),
    'arrival_time': pd.date_range('2025-10-01 02:00', periods=n, freq='3h').astype(str),
    'price': np.random.randint(2000, 15000, n),
    'delay': np.random.choice([np.nan, 0, 5, 10, 15, 30], n, p=[0.1, 0.5, 0.15, 0.1, 0.1, 0.05])
})

df.to_csv('data/raw/flights_sample.csv', index=False)

#Команда 2