import pandas as pd
import numpy as np
from statsmodels.tsa.statespace.sarimax import SARIMAX

# Load the dataset
data_path = './crop_prices_data.csv'
data = pd.read_csv(data_path)

# Month mapping (Month name to numeric value)
month_map = {month: idx + 1 for idx, month in enumerate([
    "January", "February", "March", "April", "May", "June", "July", "August",
    "September", "October", "November", "December"
])}

# Map the month names to numeric values
data['Month_num'] = data['Month'].map(month_map)

# Ensure 'Year' and 'Month_num' are integers
data['Year'] = data['Year'].astype(int)
data['Month_num'] = data['Month_num'].astype(int)

data['Date'] = pd.to_datetime(
    data[['Year', 'Month_num']].assign(DAY=1).rename(columns={'Month_num': 'month'}),
    errors='coerce'
)

# Drop any rows where the date conversion failed (optional)
data = data.dropna(subset=['Date'])

# Ensure the data is sorted by date
data = data.sort_values(by='Date')

# Initialize the crop and state list
crops = data['Crop'].unique()
states = data['State'].unique()

# Function to forecast crop prices using SARIMAX
def forecast_crop_price(crop_data, months_to_forecast=12):
    crop_data = crop_data.set_index('Date')
    crop_data = crop_data['Price (₹/Quintal)']

    # Ensure there is enough data for SARIMAX
    if len(crop_data) < 24:  # At least 2 years of data for seasonality modeling
        print("Not enough data for SARIMAX model.")
        return None, None

    # Define SARIMAX model with seasonal order
    model = SARIMAX(
        crop_data,
        order=(1, 1, 1),          # Non-seasonal (p, d, q)
        seasonal_order=(1, 1, 1, 12),  # Seasonal (P, D, Q, s) - s=12 for monthly data
        enforce_stationarity=False,
        enforce_invertibility=False
    )
    model_fit = model.fit(disp=False)

    # Forecast future prices
    forecast = model_fit.forecast(steps=months_to_forecast)
    future_dates = pd.date_range(crop_data.index[-1], periods=months_to_forecast + 1, freq='MS')[1:]

    return future_dates, forecast

# Function to update the forecast based on the selected crop and state
def get_forecast(crop, state):
    crop_data = data[(data['Crop'] == crop) & (data['State'] == state)]
    future_dates, forecast = forecast_crop_price(crop_data)
    return future_dates, forecast

# Function to get the previous 12 months of actual data
def get_previous_twelve_months(crop, state):
    crop_data = data[(data['Crop'] == crop) & (data['State'] == state)]
    crop_data = crop_data.set_index('Date')
    crop_data = crop_data['Price (₹/Quintal)']
    return crop_data[-12:]