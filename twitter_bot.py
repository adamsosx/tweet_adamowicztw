import tweepy
import time
import requests
import json
from datetime import datetime, timezone
import logging
import os

# Dodane do obsługi uploadu grafiki
from tweepy import OAuth1UserHandler, API

# Konfiguracja logowania
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()] # Logowanie do konsoli/outputu Akcji
)

# Klucze API odczytywane ze zmiennych środowiskowych
api_key = os.getenv("TWITTER_API_KEY")
api_secret = os.getenv("TWITTER_API_SECRET")
access_token = os.getenv("BOT1_ACCESS_TOKEN")
access_token_secret = os.getenv("BOT1_ACCESS_TOKEN_SECRET")

# URL API outlight.fun - (1h timeframe)
OUTLIGHT_API_URL = "https://old.outlight.fun/api/tokens/most-called?timeframe=1h"

def get_top_tokens():
    """Pobiera dane z API outlight.fun i zwraca top 5 tokenów, licząc tylko kanały z win_rate > 30%"""
    try:
        response = requests.get(OUTLIGHT_API_URL, verify=False)
        response.raise_for_status()
        data = response.json()

        tokens_with_filtered_calls = []
        for token in data:
            channel_calls = token.get('channel_calls', [])
            # Licz tylko kanały z win_rate > 30%
            calls_above_30 = [call for call in channel_calls if call.get('win_rate', 0) > 30]
            count_calls = len(calls_above_30)
            if count_calls > 0:
                token_copy = token.copy()
                token_copy['filtered_calls'] = count_calls
                tokens_with_filtered_calls.append(token_copy)

        # Sortuj po liczbie filtered_calls malejąco
        sorted_tokens = sorted(tokens_with_filtered_calls, key=lambda x: x.get('filtered_calls', 0), reverse=True)
        # Zwracamy Top 5
        top_5 = sorted_tokens[:5]
        return top_5
    except Exception as e:
        logging.error(f"Unexpected error in get_top_tokens: {e}")
        return None

def format_main_tweet(top_2_tokens):
    """Format tweet with top 2 tokens."""
    tweet = f"🚀Top 2 Most 📞 1h\n\n"
    medals = ['🥇', '🥈']
    for i, token in enumerate(top_2_tokens, 0):
        calls = token.get('filtered_calls', 0)
        symbol = token.get('symbol', 'Unknown')
        address = token.get('address', 'No Address Provided')
        medal = medals[i]
        tweet += f"{medal} ${symbol}\n"
        tweet += f"{address}\n"
        tweet += f"📞 {calls}\n\n"
    tweet = tweet.rstrip('\n') + '\n'
    tweet += "📊 Get real-time sniper signals from top KOLs 🚀 outlight.fun\n"
    tweet += "#SOL #Outlight"
    return tweet




def main():
    logging.info("GitHub Action: Bot execution started.")

    if not all([api_key, api_secret, access_token, access_token_secret]):
        logging.error("CRITICAL: One or more Twitter API keys are missing from environment variables. Exiting.")
        return

    try:
        # Klient v2
        client = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_token_secret
        )
        me = client.get_me()
        logging.info(f"Successfully authenticated on Twitter as @{me.data.username}")

        # Klient v1.1 do uploadu grafiki
        auth_v1 = OAuth1UserHandler(api_key, api_secret, access_token, access_token_secret)
        api_v1 = API(auth_v1)
    except tweepy.TweepyException as e:
        logging.error(f"Tweepy Error creating Twitter client or authenticating: {e}")
        return
    except Exception as e:
        logging.error(f"Unexpected error during Twitter client setup: {e}")
        return

    top_tokens = get_top_tokens()
    if not top_tokens:
        logging.warning("Failed to fetch top tokens or no tokens returned. Skipping tweet.")
        return

    # Przygotowanie i wysłanie głównego tweeta (tokeny 1-2)
    main_tweet_text = format_main_tweet(top_tokens[:2])
    logging.info(f"Prepared main tweet ({len(main_tweet_text)} chars):")
    logging.info(main_tweet_text)

    if len(main_tweet_text) > 280:
        logging.warning(f"Generated main tweet is too long ({len(main_tweet_text)} chars).")

    try:
        # --- Dodanie grafiki do głównego tweeta ---
        image_path = os.path.join("images", "mont.gif")
        media_id = None
        if not os.path.isfile(image_path):
            logging.error(f"Image file not found: {image_path}. Sending tweet without image.")
        else:
            try:
                media = api_v1.media_upload(image_path)
                media_id = media.media_id
                logging.info(f"Image uploaded successfully. Media ID: {media_id}")
            except Exception as e:
                logging.error(f"Error uploading image: {e}. Sending tweet without image.")

        # Wysyłanie głównego tweeta
        response_main_tweet = client.create_tweet(
            text=main_tweet_text,
            media_ids=[media_id] if media_id else None
        )
        main_tweet_id = response_main_tweet.data['id']
        logging.info(f"Main tweet sent successfully! Tweet ID: {main_tweet_id}")

    except tweepy.TooManyRequests as e:
        reset_time = int(e.response.headers.get('x-rate-limit-reset', 0))
        current_time = int(time.time())
        wait_time = max(reset_time - current_time + 10, 60)
        logging.error(f"Rate limit exceeded. Need to wait {wait_time} seconds before retrying")
    except tweepy.TweepyException as e:
        logging.error(f"Twitter API error sending tweet: {e}")
    except Exception as e:
        logging.error(f"Unexpected error sending tweet: {e}")

    logging.info("GitHub Action: Bot execution finished.")

if __name__ == "__main__":
    if 'requests' in globals() and hasattr(requests, 'packages') and hasattr(requests.packages, 'urllib3'):
        try:
            requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)
            logging.warning("SSL verification is disabled for requests (verify=False). This is not recommended.")
        except AttributeError:
            logging.warning("Could not disable InsecureRequestWarning for requests.")
    main() 
