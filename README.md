# Telegram Movie Recommendation Bot

## Overview

This Telegram bot provides movie recommendations, specifically targeting Indian movies and popular films from around the world. The bot fetches movie data from The Movie Database (TMDb) and allows users to receive updates about new releases and trending movies.

## Features

- **Movie Recommendations from India**: Sends random Indian movies with a rating above 55%.
- **International Movie Recommendations**: Sends random movies from any country with a rating above 60%.
- **New Movie Updates**: Sends updates about upcoming movies.
- **Interactive Buttons**: Each movie post includes a button to learn more about the movie.
- **User Interaction**: Users are acknowledged when they interact with the bot.

## Technologies Used

- **Python**: The main programming language for the bot.
- **Flask**: Used for creating a web interface to display the latest posted movies.
- **python-telegram-bot**: Library for interacting with the Telegram Bot API.
- **Requests**: For making HTTP requests to the TMDb API.
- **PyMongo**: For MongoDB integration to store user and movie data.

## Requirements

Make sure you have the following installed:

- Python 3.x
- MongoDB (or access to MongoDB Atlas)

### Install Dependencies

To install the required packages, run:

```bash
pip install -r requirements.txt
