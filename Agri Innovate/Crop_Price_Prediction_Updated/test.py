from forecast import get_forecast

# Get the forecast for 'Rice' in 'Andhra Pradesh'
future_dates, forecast = get_forecast('rice', 'Madhya Pradesh')

# Print the forecasted prices
for date, price in zip(future_dates, forecast):
    print(f"{date.strftime('%b %Y')}: ₹{price:.2f}")
