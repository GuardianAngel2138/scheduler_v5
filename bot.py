from flask import Flask, request, render_template, redirect, url_for, send_file
import requests
from pymongo import MongoClient
from pytz import timezone
import config
from datetime import datetime
import time
import threading
from gridfs import GridFS
import os
from bson import ObjectId

app = Flask(__name__)

# Configure upload folder
UPLOAD_FOLDER = 'uploads/'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Initialize MongoDB and GridFS
client = MongoClient(config.MONGODB_URI)
db = client.telegram_bot
collection = db.scheduled_messages
fs = GridFS(db)

# Timezone configuration for India
IST = timezone('Asia/Kolkata')

# Route for displaying scheduled messages and the form
@app.route('/')
def index():
    # Retrieve all scheduled messages to display in the table
    scheduled_messages = list(collection.find())
    current_time = datetime.now(IST)  # Timezone-aware current time

    # Ensure all message times are timezone-aware
    for message in scheduled_messages:
        if message['time'].tzinfo is None:
            message['time'] = IST.localize(message['time'])

        # Format the time in IST for display in the template
        message['scheduled_time_str'] = message['time'].strftime('%Y-%m-%d %H:%M')

        # Calculate the time left for display
        time_left = (message['time'] - current_time).total_seconds()
        if time_left > 0:
            hours, remainder = divmod(time_left, 3600)
            minutes, seconds = divmod(remainder, 60)
            message['time_left_str'] = f"{int(hours)} hours, {int(minutes)} minutes, {int(seconds)} seconds"
        else:
            message['time_left_str'] = "Time's up!"

    return render_template('index.html', scheduled_messages=scheduled_messages, current_time=current_time)

# Route to handle scheduling messages
@app.route('/schedule', methods=['POST'])
def schedule():
    try:
        datetime_str = request.form.get('datetime')
        caption = request.form.get('caption')
        image_file = request.files.get('image_file')

        if not datetime_str or not caption or not image_file:
            return "Error: Missing data. Please make sure all fields are filled out correctly.", 400

        file_id = fs.put(image_file.read(), filename=image_file.filename)

        schedule_time = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
        schedule_time = IST.localize(schedule_time)

        collection.insert_one({
            "chat_id": config.CHAT_ID,
            "image_file_id": file_id,
            "caption": caption,
            "time": schedule_time,
            "status": "pending"
        })

        return redirect(url_for('index'))
    except Exception as e:
        return f"Error: {str(e)}", 500

# Route to delete a message (Method updated to POST)
@app.route('/delete/<message_id>', methods=['POST'])
def delete_message(message_id):
    try:
        result = collection.delete_one({"_id": ObjectId(message_id)})
        if result.deleted_count > 0:
            return '', 200
        else:
            return '', 404
    except Exception as e:
        return '', 500

# Route to retrieve and serve an image from GridFS
@app.route('/image/<file_id>')
def get_image(file_id):
    try:
        image_file = fs.get(ObjectId(file_id))
        return send_file(image_file, mimetype=image_file.content_type)
    except Exception as e:
        return "Error: Image not found.", 404

# Function to send scheduled messages
def send_scheduled_images():
    current_time = datetime.now(IST)
    scheduled_images = collection.find({"time": {"$lte": current_time}, "status": "pending"})

    for image in scheduled_images:
        group_id = image['chat_id']
        file_id = image['image_file_id']
        caption = f"*{image['caption']}*"

        collection.update_one({"_id": image["_id"]}, {"$set": {"status": "in-progress"}})

        try:
            image_file = fs.get(file_id)

            url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendPhoto"
            files = {'photo': image_file}
            response = requests.post(url, data={"chat_id": group_id, "caption": caption, "parse_mode": "Markdown"}, files=files)

            if response.status_code == 200:
                confirmation_text = f"Message sent successfully to {group_id}."
                confirmation_url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage"
                requests.post(confirmation_url, data={"chat_id": config.OWNER_CHAT_ID, "text": confirmation_text})

                collection.update_one({"_id": image["_id"]}, {"$set": {"status": "sent"}})
            else:
                error_text = f"Failed to send message to {group_id}. Error: {response.text}"
                requests.post(f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage",
                              data={"chat_id": config.OWNER_CHAT_ID, "text": error_text})
        except Exception as e:
            print(f"Error sending message: {e}")

# Background task to check for and send scheduled images periodically
def scheduled_task():
    while True:
        send_scheduled_images()
        time.sleep(60)

def start_background_tasks():
    threading.Thread(target=scheduled_task, daemon=True).start()

if __name__ == "__main__":
    start_background_tasks()
    app.run(debug=True)
