import os
import datetime
import io
import csv
import random
import string

from flask import Flask, render_template, request, redirect, url_for, send_file, jsonify
import pymongo
from bson.objectid import ObjectId

# For generating barcode images
from barcode import Code128
from barcode.writer import ImageWriter

# For Tashkent timezone
import pytz

# ---- Monkey-patch to fix FreeTypeFont.getsize error ----
import barcode.writer
from PIL import ImageFont

def _getsize_patch(self, text, *args, **kwargs):
    # Use getbbox to calculate width and height
    bbox = self.getbbox(text)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    return (width, height)

ImageFont.FreeTypeFont.getsize = _getsize_patch
# ---------------------------------------------------------

app = Flask(__name__)
app.config['SECRET_KEY'] = 'yoursecretkey'

# Create static folder for barcodes if not exist
os.makedirs('static/barcodes', exist_ok=True)

# Replace with your MongoDB Atlas connection string
MONGO_URI = "mongodb+srv://nurmuhammadburiev:N9868183nurik@canteen-kassa.udxts.mongodb.net/?retryWrites=true&w=majority&appName=Canteen-kassa"

try:
    client = pymongo.MongoClient(MONGO_URI)
    db = client["canteen"]
    users_collection = db["users"]
    meals_collection = db["meals"]
    print("Successfully connected to MongoDB Atlas.")
except Exception as e:
    print("Error connecting to MongoDB Atlas:", e)

def generate_unique_code(length=8):
    """Generate a random alphanumeric string for the user's unique code."""
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

def create_barcode(content, filepath):
    """
    Generate a Code128 barcode (using ImageWriter) for the given content
    and save it to filepath.
    """
    code128 = Code128(content, writer=ImageWriter())
    code128.save(filepath)

@app.route('/')
def index():
    """
    Main page:
    - Displays a form to add a user (auto-generates code if none provided).
    - Shows a list of all users along with their barcode images.
    """
    users_cursor = users_collection.find()
    users = []
    for user in users_cursor:
        user['_id'] = str(user['_id'])
        users.append(user)
    return render_template('index.html', users=users)

@app.route('/scan', methods=['POST'])
def scan():
    """
    AJAX endpoint for scanning a barcode.
    Records the meal time in Tashkent time (plus 5 hours) if the user exists 
    and hasn't been recorded for today. Since the check is based on today's date,
    the status resets at midnight.
    """
    barcode_val = request.form.get('barcode', '').strip()

    # Find user by barcode value (stored under 'barcode')
    user = users_collection.find_one({"barcode": barcode_val})
    if not user:
        return jsonify({
            'status': 'error',
            'message': 'Пользователь с таким штрихкодом не найден.'
        })

    tz = pytz.timezone("Asia/Tashkent")
    today_start = datetime.datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start.replace(hour=23, minute=59, second=59)

    meal_record = meals_collection.find_one({
        "user_id": user["_id"],
        "timestamp": {"$gte": today_start, "$lte": today_end}
    })

    if meal_record:
        return jsonify({
            'status': 'fail',
            'name': user.get('name', 'No Name'),
            'message': 'Этот пользователь уже ел сегодня!'
        })
    else:
        now_tashkent = datetime.datetime.now(tz) + datetime.timedelta(hours=5)
        meals_collection.insert_one({
            "user_id": user["_id"],
            "timestamp": now_tashkent
        })
        return jsonify({
            'status': 'success',
            'name': user.get('name', 'No Name'),
            'message': 'Успешно записано питание за сегодня.'
        })

@app.route('/lookup', methods=['POST'])
def lookup():
    """
    AJAX endpoint for looking up a user by barcode without altering meal records.
    This is used in the barcodes page to verify barcode ownership.
    """
    barcode_val = request.form.get('barcode', '').strip()
    user = users_collection.find_one({"barcode": barcode_val})
    if not user:
         return jsonify({"status": "error", "message": "Пользователь с таким штрихкодом не найден."})
    user['_id'] = str(user['_id'])
    return jsonify({
         "status": "success",
         "user": {
              "name": user.get("name", ""),
              "phone": user.get("phone", ""),
              "photo_url": user.get("photo_url", ""),
              "barcode": user.get("barcode", ""),
              "barcode_image": url_for("static", filename="barcodes/barcode_" + user.get("barcode", "") + ".png")
         }
    })

@app.route('/report')
def report():
    """
    Displays a page with a form to select a date range for generating a CSV report.
    """
    return render_template('report.html')

@app.route('/download-report', methods=['POST'])
def download_report():
    """
    Generates a CSV report that contains user fields (with phone number)
    and the meal time (Asia/Tashkent time plus 5 hours) when the meal was recorded.
    """
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')

    try:
        start_dt_naive = datetime.datetime.strptime(start_date, '%Y-%m-%d')
        end_dt_naive = datetime.datetime.strptime(end_date, '%Y-%m-%d')
    except ValueError:
        return "Неверный формат даты. Используйте YYYY-MM-DD."

    tz = pytz.timezone("Asia/Tashkent")
    start_dt = tz.localize(start_dt_naive.replace(hour=0, minute=0, second=0, microsecond=0))
    end_dt = tz.localize(end_dt_naive.replace(hour=23, minute=59, second=59, microsecond=999999))

    query = {
        "timestamp": {"$gte": start_dt, "$lte": end_dt}
    }
    meals_cursor = meals_collection.find(query).sort("timestamp", 1)

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["User ID", "Name", "Phone", "Barcode", "Meal Time (Asia/Tashkent +5h)"])

    for meal in meals_cursor:
        user_id = meal.get("user_id")
        user_doc = users_collection.find_one({"_id": user_id})
        if not user_doc:
            continue

        uid_str = str(user_id)
        name = user_doc.get("name", "")
        phone = user_doc.get("phone", "")
        barcode_val = user_doc.get("barcode", "")

        meal_time = meal["timestamp"]
        tz = pytz.timezone("Asia/Tashkent")
        meal_time_tashkent = meal_time if meal_time.tzinfo else tz.localize(meal_time)
        meal_time_adjusted = meal_time_tashkent + datetime.timedelta(hours=5)
        meal_time_str = meal_time_adjusted.strftime("%Y-%m-%d %H:%M:%S")

        writer.writerow([uid_str, name, phone, barcode_val, meal_time_str])

    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name='report.csv'
    )

@app.route('/add_user', methods=['POST'])
def add_user():
    """
    Adds a new user.
    Generates a unique barcode if not provided.
    Creates a barcode image for the user.
    Replaces email with phone number.
    """
    name = request.form.get("name", "")
    phone = request.form.get("phone", "")
    photo_url = request.form.get("photo_url", "")
    barcode_val = request.form.get("barcode", "").strip()

    if not name:
        return redirect(url_for('index'))

    if not barcode_val:
        barcode_val = generate_unique_code()

    # Save barcode in the user document and generate its image
    barcode_filename = f"barcode_{barcode_val}"
    barcode_filepath = os.path.join("static", "barcodes", barcode_filename)
    create_barcode(barcode_val, barcode_filepath)

    new_user = {
        "name": name,
        "phone": phone,
        "photo_url": photo_url,
        "barcode": barcode_val,
        "barcode_image": barcode_filepath + ".png"  # Barcode writer appends .png
    }
    users_collection.insert_one(new_user)
    return redirect(url_for('index'))

@app.route('/delete_user/<uid>')
def delete_user(uid):
    """
    Deletes a user and removes their barcode image file if it exists.
    """
    try:
        obj_id = ObjectId(uid)
        user_doc = users_collection.find_one({"_id": obj_id})
        if user_doc:
            if 'barcode_image' in user_doc and os.path.exists(user_doc['barcode_image']):
                os.remove(user_doc['barcode_image'])
            users_collection.delete_one({"_id": obj_id})
    except Exception as e:
        print("Error deleting user:", e)
    return redirect(url_for('index'))

@app.route('/barcodes')
def barcodes():
    """
    Displays a page with a list of all barcodes along with the corresponding user details.
    Also provides a scanner for checking barcode ownership.
    """
    users_cursor = users_collection.find()
    users = []
    for user in users_cursor:
        user['_id'] = str(user['_id'])
        users.append(user)
    return render_template('barcodes.html', users=users)

@app.route('/meal_records')
def meal_records():
    """
    Displays a page with all meal records.
    Each record shows the user details and meal timestamp.
    """
    tz = pytz.timezone("Asia/Tashkent")
    meals = []
    for meal in meals_collection.find().sort("timestamp", -1):
        user_doc = users_collection.find_one({"_id": meal["user_id"]})
        meal["id"] = str(meal["_id"])
        if meal["timestamp"].tzinfo:
            meal_time = meal["timestamp"]
        else:
            meal_time = tz.localize(meal["timestamp"])
        meal_time_adjusted = meal_time + datetime.timedelta(hours=5)
        meal["timestamp_formatted"] = meal_time_adjusted.strftime("%Y-%m-%d %H:%M:%S")
        if user_doc:
            meal["user_name"] = user_doc.get("name", "No Name")
            meal["phone"] = user_doc.get("phone", "")
            meal["barcode"] = user_doc.get("barcode", "")
        else:
            meal["user_name"] = "Unknown"
            meal["phone"] = ""
            meal["barcode"] = ""
        meals.append(meal)
    return render_template("meal_records.html", meals=meals)

@app.route('/delete_meal/<meal_id>')
def delete_meal(meal_id):
    """
    Deletes a specific meal record from the database.
    """
    try:
        meals_collection.delete_one({"_id": ObjectId(meal_id)})
    except Exception as e:
        print("Error deleting meal record:", e)
    return redirect(url_for("meal_records"))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5055))
    app.run(debug=True, host='0.0.0.0', port=port)
