# -*- coding: utf-8 -*-
"""
Created on 14 Jan 2025

@author: KodeBuddy
"""
import sqlite3
from flask import Flask, flash, redirect, render_template, session, url_for, jsonify, request
from flask_cors import CORS
from sklearn.tree import DecisionTreeRegressor
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd
import numpy as np
import random
from datetime import datetime
import json
import requests
from crops import crop
from forecast import get_forecast, get_previous_twelve_months

app = Flask(__name__)
app.debug = True
DATABASE = 'users.db'
app.secret_key = "your_secret_key"

app.config['CORS_HEADERS'] = 'Content-Type'
CORS(app, resources={r"/ticker": {"origins": "http://localhost:port"}})



commodity_dict = {
    "gram": "static/rainfall_datasets/Gram.csv",
    
    "arhar": "static/rainfall_datasets/Arhar.csv",
    "masoor": "static/rainfall_datasets/Masoor.csv",
    
    "moong": "static/rainfall_datasets/Moong.csv",
    "rice": "static/rainfall_datasets/Rice.csv",
    
    "urad": "static/rainfall_datasets/Urad.csv",
    "wheat": "static/rainfall_datasets/Wheat.csv",
    "potato": "static/rainfall_datasets/Potato.csv",
    "onion": "static/rainfall_datasets/Onion.csv",
    "tomato": "static/rainfall_datasets/Tomato.csv",    
}

annual_rainfall = [29, 21, 37.5, 30.7, 52.6, 150, 299, 251.7, 179.2, 70.5, 39.8, 10.9]





commodity_list = []


# Data loading and saving functions
def load_crop_data(filename='crop_data.json'):
    try:
        with open(filename, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        print(f"The file {filename} was not found. Creating a new one.")
        return {}

def save_crop_data(crop_data, filename='crop_data.json'):
    with open(filename, 'w') as file:
        json.dump(crop_data, file, indent=4)



def update_farmers_count(crop_name, new_count, filename='crop_data.json'):
    crop_data = load_crop_data(filename)
    if crop_name in crop_data:
        crop_data[crop_name] = new_count
        save_crop_data(crop_data, filename)
        return f"Updated {crop_name} to {new_count} farmers."
    else:
        return "Crop not found"

# Database initialization function
def init_db():
    """Initialize the database."""
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        
        # Create or update users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phonenumber TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                state TEXT NOT NULL
            )
        """)
        
        # Crops table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS crops (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                count INTEGER DEFAULT 0
            )
        """)

        # User-Crop mapping table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_crops (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                crop_id INTEGER NOT NULL,
                state TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (crop_id) REFERENCES crops(id)
            )
        """)
        
        conn.commit()

def get_farmers_count (crop_name, state_name ):
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM user_crops WHERE crop_id = (SELECT id FROM crops WHERE name = ? AND state = ?)", (crop_name, state_name )) 
        count = cursor.fetchone()
        if count:

            return jsonify({"farmers_count": count[0]})
        else:
            return jsonify({"farmers_count": 0})
    
    return jsonify({"error": "Crop not found"})


def get_growing_crop():
    user_id = session['user_id']
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT crops.name FROM crops
            JOIN user_crops ON crops.id = user_crops.crop_id
            WHERE user_crops.user_id = ?
        """, (user_id,))
        crops = cursor.fetchall()
        return crops
    


init_db()

# Commodity Class
class Commodity:
    def __init__(self, csv_name):
        self.name = csv_name.split('/')[-1].split('.')[0]
        dataset = pd.read_csv(csv_name)
        self.X = dataset.iloc[:, :-1].values
        self.Y = dataset.iloc[:, 3].values
        self.regressor = DecisionTreeRegressor(max_depth=random.randint(7, 18))
        self.regressor.fit(self.X, self.Y)

    def predict(self, values):
        values = np.array(values).reshape(1, -1)
        return self.regressor.predict(values)[0]

# Route definitions
@app.route('/')
def index():
    if 'user_id' in session:
        context = {
                "growing_crop" :  get_growing_crop()[0][0] if len(get_growing_crop()) > 0 else "",
                "state" : session['state'] if 'state' in session else "Andhra Pradesh",
                "current_growing_crop_farmers": get_farmers_count(get_growing_crop()[0][0], session['state']).json['farmers_count'] if len(get_growing_crop()) > 0 else 0
            }
            
        
        
        return render_template('index.html', context=context,name=session['name'])   
    else:
        flash("Please log in to access the dashboard.", "warning")
        return redirect(url_for('login'))
    


@app.route('/tradedata')
def tradedata():
    return render_template('trade.html')

@app.route('/croppage')
def croppage():
    commodities = commodity_dict.keys()
    return render_template('croppage.html', commodities=commodities)
    

@app.route('/api/update_crop', methods=['POST'])
def update_crop():
    """Route to update crop selection for a user."""
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized access"}), 401

    user_id = session['user_id']
    data = request.json
    crop_name = data.get('crop')

    if not crop_name:
        return jsonify({"error": "Crop name is required"}), 400

    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()

        # Get the current crop selection for the user (if exists)
        cursor.execute("""
            SELECT c.id, c.name
            FROM user_crops uc
            JOIN crops c ON uc.crop_id = c.id
            WHERE uc.user_id = ?
        """, (user_id,))
        current_crop = cursor.fetchone()

        if current_crop:
            current_crop_id, current_crop_name = current_crop

            # Decrement the count of the previously selected crop
            cursor.execute("""
                UPDATE crops
                SET count = count - 1
                WHERE id = ? AND count > 0
            """, (current_crop_id,))

            # Remove the old crop from user_crops
            cursor.execute("""
                DELETE FROM user_crops
                WHERE user_id = ? AND crop_id = ? AND state = ?
            """, (user_id, current_crop_id, session['state']))

        # Check if the new crop exists
        cursor.execute("SELECT id FROM crops WHERE name = ?", (crop_name,))
        new_crop = cursor.fetchone()

        if not new_crop:
            # Insert the new crop into the database
            cursor.execute("INSERT INTO crops (name, count) VALUES (?, ?)", (crop_name, 1))
            new_crop_id = cursor.lastrowid
        else:
            # Increment the count of the new crop
            new_crop_id = new_crop[0]
            cursor.execute("UPDATE crops SET count = count + 1 WHERE id = ?", (new_crop_id,))

        # Add the new crop to user_crops
        cursor.execute("""
            INSERT INTO user_crops (user_id, crop_id, state)
            VALUES (?, ?, ?)
        """, (user_id, new_crop_id, session['state']))

        conn.commit()

        # Get the updated count of farmers for the new crop
        # cursor.execute("SELECT count FROM crops WHERE id = ? AND state = ?", (new_crop_id,session['state']))
        farmers_count = get_farmers_count(get_growing_crop()[0][0], session['state']).json['farmers_count'] if len(get_growing_crop()) > 0 else 0

    return jsonify({
        "message": "Crop selection updated successfully",
        "farmers_count": farmers_count
    })


    

@app.route('/api/commodities', methods=['GET'])
def get_commodities():
    url = "https://enam.gov.in/web/Liveprice_ctrl/commodity_names"
    today = datetime.today().strftime('%Y-%m-%d')
    payload = {"fromDate": today, "toDate": today}
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    try:
        response = requests.post(url, data=payload, headers=headers)
        response.raise_for_status()
        return jsonify(response.json())
    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/farmers/<crop_name>', methods=['GET'])
def get_farmers_count_api(crop_name):
    count = get_farmers_count(crop_name, session['state'])
    return jsonify({"crop_name": crop_name, "farmers_count": count})

@app.route('/api/farmers/<crop_name>', methods=['PUT'])
def update_farmers_count_api(crop_name):
    new_count = load_crop_data().get(crop_name, 0) + 1
    result = update_farmers_count(crop_name, new_count)
    return jsonify({"message": result})

@app.route('/api/farmers/<crop_name>', methods=['DELETE'])
def delete_farmers_count_api(crop_name):
    crop_data = load_crop_data()
    new_count = max(crop_data.get(crop_name, 0) - 1, 0)
    if crop_name in crop_data:
        crop_data[crop_name] = new_count
        save_crop_data(crop_data)
        return jsonify({"message": f"Deleted {crop_name}"}), 200
    else:
        return jsonify({"message": "Crop not found"}), 404
    

@app.route('/api/trade-data', methods=['POST'])
def get_trade_data():
    # Fetch trade data for a specific commodity
    data = request.json  # Expecting {"commodity": "value"} from frontend
    commodity = data.get("commodity")
    url = "https://enam.gov.in/web/Liveprice_ctrl/trade_data_list_1"
    payload = {
        "language": "en",
        "commodity": commodity,
        "fromDate": datetime.today().strftime('%Y-%m-%d'),
        "toDate": datetime.today().strftime('%Y-%m-%d')
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    try:
        response = requests.post(url, data=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        return jsonify(data)
    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500
    


@app.route('/commodity/<name>', methods=['GET', 'POST'])
def crop_profile(name):

    # if post
    if request.method == 'POST':
        state = request.form['state'] if request.form['state'] else session['state']
    else:
        state = session['state']

    future_dates, forecast_crop_values = TwelveMonthsForecast(name, state)
    
    forecast_x = [i.strftime('%b %Y') for i in future_dates]
    forecast_y = forecast_crop_values
    previous_x, previous_y = PreviousTwelveMonths(name, state)
    farmers_count = get_farmers_count(name, state ).json['farmers_count']
    current_price = CurrentMonth(name)
    min_crop = ['Jan 2025',float('inf')]
    for i, ele in enumerate(forecast_y):
        if ele < min_crop[1]:
            min_crop = [forecast_x[i],ele]
    max_crop = [0,0]
    for i, ele in enumerate(forecast_y):
        if ele > max_crop[1]:
            max_crop = [forecast_x[i],ele]
    # print(max_crop)
    # print(min_crop)
    # print(forecast_crop_values)
    # print(prev_crop_values)
    # print(str(forecast_x))
    crop_data = crop(name)
    context = {
        "name":name,
        "min_crop": min(forecast_crop_values),
        "max_crop": max(forecast_crop_values),
        "forecast_values": forecast_crop_values,
        "forecast_x": forecast_x,
        "previous_x": str(previous_x),
        "previous_y": previous_y,
        "forecast_y":forecast_y,
        "min_crop": min_crop,
        "max_crop": max_crop,
        "current_price": current_price,
        "image_url":crop_data[0],
        "prime_loc":crop_data[1],
        "type_c":crop_data[2],
        "export":crop_data[3],
        "farmers_count": farmers_count,
        "state": state
    }
    return render_template('commodity.html', context=context)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        phonenumber = request.form['phonenumber']
        password = request.form['password']
        state = request.form['state']
        hashed_password = generate_password_hash(password)

        try:
            with sqlite3.connect(DATABASE) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO users (name, phonenumber, password, state)
                    VALUES (?, ?, ?, ?)
                """, (name, phonenumber, hashed_password, state))
                conn.commit()
            flash("Registration successful! Please log in.", "success")
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash("Phone number already exists. Please use a different one.", "danger")
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        phonenumber = request.form['phonenumber']
        password = request.form['password']

        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE phonenumber = ?", (phonenumber,))
            user = cursor.fetchone()

        if user and check_password_hash(user[3], password):
            session['user_id'] = user[0]
            session['name'] = user[1]
            session['state'] = user[4]
            flash("Login successful!", "success")
            return redirect(url_for('index'))
        else:
            flash("Invalid phone number or password. Please try again.", "danger")

    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' in session:
        return render_template('dashboard.html', name=session['name'])
    else:
        flash("Please log in to access the dashboard.", "warning")
        return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    
    return redirect(url_for('login'))












def CurrentMonth(name):
    current_month = datetime.now().month
    current_year = datetime.now().year
   
    # check current price in forecast data
    forecast_data = TwelveMonthsForecast(name, session['state'])
    forecast_dates = forecast_data[0]
    forecast_values = forecast_data[1]
    current_price = forecast_values[current_month - 1]
    return current_price

def PreviousTwelveMonths(name, state):
    logged_user_state = state
    if name == "rice":
        name = "Rice"
    if name == "soyabean":
        name = "Soybean"

   
    
    name = name[0].upper() + name[1:]
    
    previous_twelve_months_crop_data = get_previous_twelve_months(name, logged_user_state)
    previous_dates = [i.strftime('%b %Y') for i in previous_twelve_months_crop_data.index]
    previous_values = previous_twelve_months_crop_data.values.tolist()
    return previous_dates, previous_values


def TwelveMonthsForecast(name, state):
    current_month = datetime.now().month
    current_year = datetime.now().year
    if name == "rice":
        name = "Rice"
    if name == "soyabean":
        name = "Soybean"
    name = name[0].upper() + name[1:]

    logged_user_state = state

    
    future_dates , crop_price = get_forecast(name, logged_user_state)

    future_dates = []
    # 12 months from now
    for i in range(1, 13):
        current_month += 1
        if current_month > 12:
            current_month = 1
            current_year += 1
        future_dates.append(datetime(current_year, current_month, 1))
    # future_dates = [i.strftime('%b %Y') for i in future_dates]
    # print(future_dates)


    # max_crop = max(crop_price.tolist())
    # min_crop = min(crop_price.tolist())


    return future_dates , crop_price.tolist()





if __name__ == "__main__":
    gram = Commodity(commodity_dict["gram"])
    commodity_list.append(gram)
    """barley = Commodity(commodity_dict["barley"])
    commodity_list.append(barley)"""
    arhar = Commodity(commodity_dict["arhar"])
    commodity_list.append(arhar)
    masoor = Commodity(commodity_dict["masoor"])
    commodity_list.append(masoor)
    """jowar = Commodity(commodity_dict["jowar"])
    commodity_list.append(jowar)
    maize = Commodity(commodity_dict["maize"])
    commodity_list.append(maize)"""
    moong = Commodity(commodity_dict["moong"])
    commodity_list.append(moong)
    rice = Commodity(commodity_dict["rice"])
    commodity_list.append(rice)
    """soyabean = Commodity(commodity_dict["soyabean"])
    commodity_list.append(soyabean)
    sugarcane = Commodity(commodity_dict["sugarcane"])
    commodity_list.append(sugarcane)"""
    urad = Commodity(commodity_dict["urad"])
    commodity_list.append(urad)
    wheat = Commodity(commodity_dict["wheat"])
    commodity_list.append(wheat)

    app.run()





