from flask import Flask, request, render_template, redirect, url_for
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

# Route for scheduling images via a web form
@app.route('/')
def index():
    # Retrieve all scheduled messages to display in the table
    scheduled_messages = list(collection.find())
    current_time = datetime.now(IST)  # Timezone-aware current time

    # Ensure all message times are timezone-aware
    for message in scheduled_messages:
        # Convert 'time' to timezone-aware datetime if it is not
        if message['time'].tzinfo is None:
            message['time'] = IST.localize(message['time'])

    return render_template('index.html', scheduled_messages=scheduled_messages, current_time=current_time)

@app.route('/schedule', methods=['POST'])
def schedule():
    try:
        datetime_str = request.form.get('datetime')
        caption = request.form.get('caption')
        image_file = request.files.get('image_file')

        # Check if all required data is present
        if not datetime_str or not caption or not image_file:
            return "Error: Missing data. Please make sure all fields are filled out correctly.", 400

        # Save the image to GridFS
        file_id = fs.put(image_file.read(), filename=image_file.filename)

        # Convert to IST time
        schedule_time = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
        schedule_time = IST.localize(schedule_time)

        # Save to MongoDB
        collection.insert_one({
            "chat_id": config.CHAT_ID,  # Use default chat ID from config
            "image_file_id": file_id,
            "caption": caption,
            "time": schedule_time,
            "status": "pending"
        })

        # Redirect back to the main page
        return redirect(url_for('index'))
    except Exception as e:
        return f"Error: {str(e)}", 500

@app.route('/delete/<message_id>', methods=['DELETE'])
def delete_message(message_id):
    try:
        # Find the message by ID and delete it
        result = collection.delete_one({"_id": ObjectId(message_id)})  # Use ObjectId for MongoDB
        if result.deleted_count > 0:
            return '', 200  # Successfully deleted
        else:
            return '', 404  # Not found
    except Exception as e:
        print(f"Error deleting message: {e}")
        return '', 500  # Internal server error

@app.route('/image/<file_id>')
def get_image(file_id):
    try:
        # Retrieve the image from GridFS
        image_file = fs.get(file_id)
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
        caption = f"*{image['caption']}*"  # Make the caption bold using Markdown

        # Update status to "in-progress" to avoid duplicates
        collection.update_one({"_id": image["_id"]}, {"$set": {"status": "in-progress"}})

        try:
            # Retrieve the image from GridFS
            image_file = fs.get(file_id)

            # Send the image to the group or channel
            url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendPhoto"
            files = {'photo': image_file}
            response = requests.post(url, data={"chat_id": group_id, "caption": caption, "parse_mode": "Markdown"}, files=files)

            if response.status_code == 200:
                # Send confirmation to the owner
                confirmation_text = f"Message sent successfully to {group_id}."
                confirmation_url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage"
                requests.post(confirmation_url, data={"chat_id": config.OWNER_CHAT_ID, "text": confirmation_text})

                # Update status to 'sent'
                collection.update_one({"_id": image["_id"]}, {"$set": {"status": "sent"}})
            else:
                # Handle failed message
                error_text = f"Failed to send message to {group_id}. Error: {response.text}"
                requests.post(f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage",
                              data={"chat_id": config.OWNER_CHAT_ID, "text": error_text})
        except Exception as e:
            print(f"Error sending message: {e}")

# Background task to check for and send scheduled images periodically
def scheduled_task():
    while True:
        send_scheduled_images()
        time.sleep(60)  # Check every minute

def start_background_tasks():
    threading.Thread(target=scheduled_task, daemon=True).start()

if __name__ == "__main__":
    start_background_tasks()
    app.run(debug=True)
