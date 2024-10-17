import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler
from threading import Thread
from flask import Flask, render_template
import asyncio
import logging
import random
import re
import requests
import pymongo
from config import BOT_TOKEN, GROUP_ID, MONGO_URI, TMDB_API_KEY, CHECK_INTERVAL, RANDOM_DELAY_IN, RANDOM_DELAY_ANY, RANDOM_DELAY_NEW

# Initialize Flask app
app = Flask(__name__)

# MongoDB setup
client = pymongo.MongoClient(MONGO_URI)
db = client['movie_bot']
collection = db['posted_movies']
users_collection = db['users']  # Collection for storing user information

# Telegram bot setup using Application
application = Application.builder().token(BOT_TOKEN).build()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

@app.route('/')
def index():
    last_posted = collection.find().sort('posted_at', -1).limit(5)
    last_movies = list(last_posted) if collection.estimated_document_count() > 0 else []
    return render_template('index.html', last_movies=last_movies)

def escape_markdown_v2(text):
    return re.sub(r'([_\*\[\]\(\)~`>#+\-=|{}\.!])', r'\\\1', text)

def get_tmdb_updates(endpoint, params=None):
    logging.info(f"Fetching movies from TMDb: {endpoint}")
    try:
        url = f"https://api.themoviedb.org/3/{endpoint}?api_key={TMDB_API_KEY}&language=en-US"
        if params:
            url += '&' + '&'.join([f"{k}={v}" for k, v in params.items()])
        response = requests.get(url)
        return response.json()
    except Exception as e:
        logging.error(f"Error fetching from TMDb: {e}")
        return {}

def get_movie_details(movie_id):
    return get_tmdb_updates(f"movie/{movie_id}", params={'append_to_response': 'credits,watch/providers'})

def format_movie_details(movie):
    title = movie['title']
    tmdb_url = f"https://www.themoviedb.org/movie/{movie['id']}"
    rating = movie.get('vote_average', 'N/A')
    country = movie.get('production_countries', [{}])[0].get('name', 'N/A')
    actors = ', '.join([actor['name'] for actor in movie.get('credits', {}).get('cast', [])[:3]]) or 'N/A'
    watch_providers = movie.get('watch/providers', {}).get('results', {}).get('US', {}).get('flatrate', [])
    where_to_view = '@' + ', @'.join([provider['provider_name'] for provider in watch_providers]) if watch_providers else 'N/A'

    return {
        'title': title,
        'tmdb_url': tmdb_url,
        'rating': rating,
        'country': country,
        'actors': actors,
        'where_to_view': where_to_view,
        'poster_url': f"https://image.tmdb.org/t/p/w500{movie['poster_path']}" if movie.get('poster_path') else None
    }

def store_user(user_id, username):
    if not users_collection.find_one({'user_id': user_id}):
        users_collection.insert_one({'user_id': user_id, 'username': username})
        logging.info(f"Stored new user: {user_id} - {username}")
    else:
        logging.info(f"User {user_id} already exists.")

async def button_click(update: Update, context):
    query = update.callback_query
    await query.answer()

    # Retrieve user info when they click the button
    user_id = query.from_user.id
    username = query.from_user.username or query.from_user.first_name

    # Store user info in MongoDB
    store_user(user_id, username)

    # Optionally, send a message to acknowledge button click
    await query.edit_message_text(text=f"Thanks for interacting, {username}! You can check more details in the upcoming movies.")

async def post_movie_to_telegram(movie_details):
    title = escape_markdown_v2(movie_details['title'])
    tmdb_url = escape_markdown_v2(movie_details['tmdb_url'])
    rating = escape_markdown_v2(str(movie_details['rating']))
    actors = escape_markdown_v2(movie_details['actors'])
    country = escape_markdown_v2(movie_details['country'])
    where_to_view = escape_markdown_v2(movie_details['where_to_view'])

    message = (
        f"*[{title}]({tmdb_url})*\n"
        f"*Rating:* *{rating}*\n"
        f"*Actors:* *{actors}*\n"
        f"*Country of Origin:* *{country}*\n"
        f"*Watch on:* @{where_to_view}"
    )

    keyboard = [[InlineKeyboardButton("Know More", callback_data="movie_info")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        poster = requests.get(movie_details['poster_url']).content if movie_details['poster_url'] else None
        if poster:
            await application.bot.send_photo(chat_id=GROUP_ID, photo=poster, caption=message, parse_mode='MarkdownV2', reply_markup=reply_markup)
        else:
            await application.bot.send_message(chat_id=GROUP_ID, text=message, parse_mode='MarkdownV2', disable_web_page_preview=True, reply_markup=reply_markup)
    except Exception as e:
        logging.error(f"Error posting {title} to Telegram: {e}")

async def send_random_movie_from_india():
    data = get_tmdb_updates('discover/movie', params={'region': 'IN', 'vote_average.gte': 5.5, 'sort_by': 'popularity.desc'})
    if data.get('results', []):
        for _ in range(2):
            random_movie = random.choice(data['results'])
            await post_movie_to_telegram(format_movie_details(get_movie_details(random_movie['id'])))
            await asyncio.sleep(random.uniform(*RANDOM_DELAY_IN))  # Add random delay

async def send_random_movie_any_country():
    data = get_tmdb_updates('discover/movie', params={'vote_average.gte': 6.0, 'sort_by': 'popularity.desc'})
    if data.get('results', []):
        for _ in range(2):
            random_movie = random.choice(data['results'])
            await post_movie_to_telegram(format_movie_details(get_movie_details(random_movie['id'])))
            await asyncio.sleep(random.uniform(*RANDOM_DELAY_ANY))  # Add random delay

async def send_new_movie_updates():
    data = get_tmdb_updates('movie/upcoming')
    if data.get('results', []):
        for _ in range(2):
            random_movie = random.choice(data['results'])
            await post_movie_to_telegram(format_movie_details(get_movie_details(random_movie['id'])))
            await asyncio.sleep(random.uniform(*RANDOM_DELAY_NEW))  # Add random delay

async def check_and_post_updates():
    while True:
        await send_random_movie_from_india()
        await send_random_movie_any_country()
        await send_new_movie_updates()
        await asyncio.sleep(CHECK_INTERVAL)

def start_async_tasks():
    asyncio.run(check_and_post_updates())

# Add button click handler
application.add_handler(CallbackQueryHandler(button_click))

if __name__ == "__main__":
    Thread(target=start_async_tasks).start()
    application.run_polling()
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
