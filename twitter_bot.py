import tweepy
import time
import requests
import json
from datetime import datetime, timezone
import logging
import os
from tweepy import OAuth1UserHandler, API

# ... (importy i konfiguracja OpenAI bez zmian) ...
# Try to import OpenAI - handle different versions
openai_client = None
try:
    # Try new OpenAI v1.x
    from openai import OpenAI
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if openai_api_key:
        openai_client = OpenAI(api_key=openai_api_key)
        logging.info("OpenAI v1.x client initialized")
except ImportError:
    try:
        # Try old OpenAI v0.x
        import openai
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if openai_api_key:
            openai.api_key = openai_api_key
            openai_client = "legacy"  # Flag for legacy usage
            logging.info("OpenAI v0.x client initialized")
    except ImportError:
        logging.warning("OpenAI library not available")
        openai_client = None

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

# API keys
api_key = os.getenv("TWITTER_API_KEY")
api_secret = os.getenv("TWITTER_API_SECRET")
access_token = os.getenv("TWITTER_ACCESS_TOKEN")
access_token_secret = os.getenv("TWITTER_ACCESS_TOKEN_SECRET")

OUTLIGHT_API_URL = "https://outlight.fun/api/tokens/most-called?timeframe=1h"

# ... (funkcje safe_tweet_with_retry i safe_media_upload bez zmian) ...
def safe_tweet_with_retry(client, text, media_ids=None, in_reply_to_tweet_id=None, max_retries=3):
    """
    Safely send tweet with rate limit handling and retry logic
    """
    for attempt in range(max_retries):
        try:
            response = client.create_tweet(
                text=text,
                media_ids=media_ids,
                in_reply_to_tweet_id=in_reply_to_tweet_id
            )
            logging.info(f"Tweet sent successfully! ID: {response.data['id']}")
            return response
            
        except tweepy.TooManyRequests as e:
            reset_time = int(e.response.headers.get('x-rate-limit-reset', 0))
            current_time = int(time.time())
            wait_time = max(reset_time - current_time + 60, 300)
            
            logging.warning(f"Rate limit exceeded. Attempt {attempt + 1}/{max_retries}")
            logging.warning(f"Waiting {wait_time} seconds before retry")
            
            if attempt < max_retries - 1:
                time.sleep(wait_time)
            else:
                logging.error("Maximum retry attempts exceeded. Tweet not sent.")
                raise e
                
        except tweepy.Forbidden as e:
            logging.error(f"Authorization error: {e}")
            raise e
            
        except tweepy.BadRequest as e:
            logging.error(f"Bad request (possibly tweet too long?): {e}")
            raise e
            
        except Exception as e:
            logging.error(f"Unexpected error on attempt {attempt + 1}: {e}")
            if attempt == max_retries - 1:
                raise e
            time.sleep(30)
    
    return None

def get_top_tokens():
    """Fetch data from outlight.fun API"""
    try:
        response = requests.get(OUTLIGHT_API_URL)
        response.raise_for_status()
        data = response.json()

        tokens_with_filtered_calls = []
        for token in data:
            channel_calls = token.get('channel_calls', [])
            calls_above_30 = [call for call in channel_calls if call.get('win_rate', 0) > 30]
            count_calls = len(calls_above_30)
            if count_calls > 0:
                token_copy = token.copy()
                token_copy['filtered_calls'] = count_calls
                tokens_with_filtered_calls.append(token_copy)

        sorted_tokens = sorted(tokens_with_filtered_calls, key=lambda x: x.get('filtered_calls', 0), reverse=True)
        top_3 = sorted_tokens[:3]
        return top_3
    except Exception as e:
        logging.error(f"Error fetching data from API: {e}")
        return None

# ZMIANA: Całkowicie usunęliśmy funkcję format_tweet, bo nie ma już tweeta zapasowego.

def generate_ai_tweet(top_3_tokens):
    """Generate intelligent tweet using OpenAI based on token data"""
    # ZMIANA: Jeśli AI nie jest dostępne, kończymy, a nie używamy zapasowej opcji.
    if not openai_client:
        logging.error("OpenAI client not available. Cannot generate tweet.")
        return None
        
    try:
        token_data = []
        for i, token in enumerate(top_3_tokens, 1):
            calls = token.get('filtered_calls', 0)
            symbol = token.get('symbol', 'Unknown')
            address = token.get('address', 'No Address')
            short_address = f"{address[:4]}...{address[-4]}" if len(address) > 8 else address
            token_data.append(f"{i}. ${symbol} - {calls} calls - CA: {short_address}")
        
        data_summary = "\n".join(token_data)
        total_calls = sum(token.get('filtered_calls', 0) for token in top_3_tokens)
        
        system_prompt = """You are MONTY, an AI agent with a distinctive style for crypto content, responding in English.

PERSONALITY & STYLE:
- Brilliant and witty
- Use crypto-appropriate metaphors
- Very short texts, abbreviated thoughts, no long full sentences
- Funny and slightly witty but never rude

CONTENT FOCUS:
- Crypto analytics and token data.
- **When mentioning a token, include its symbol and its shortened Contract Address (CA) for user convenience.**
- Use effective hooks in post beginnings.
- Solana memes niche specialty.

LANGUAGE & LIMITS:
- English B1/B2 level max.
- Keep within X character limits.
- Make each post unique and engaging."""
        
        prompt = f"""Create a crypto Twitter post about the most called tokens in the last hour as MONTY.

DATA:
{data_summary}

Total calls tracked: {total_calls}

Create 1 engaging post:
- Start with a strong hook.
- **Include the token data (Symbol and CA) naturally.**
- Use MONTY's witty, brief style.
- Max 270 chars preferred.
- Include relevant emojis.
- Focus on Solana/meme insights.

Just return the tweet text, no labels."""

        logging.info("Generating AI tweets...")
        
        if openai_client == "legacy":
            import openai
            response = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}], max_tokens=300, temperature=0.8)
            ai_response = response.choices[0].message.content.strip()
        else:
            response = openai_client.chat.completions.create(model="gpt-3.5-turbo", messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}], max_tokens=300, temperature=0.8)
            ai_response = response.choices[0].message.content.strip()
        
        logging.info(f"AI Response received: {len(ai_response)} characters")
        
        main_tweet = ai_response.strip()
        
        if not main_tweet:
            # ZMIANA: Jeśli AI zwróci pustą odpowiedź, logujemy błąd i zwracamy None
            logging.error("AI returned an empty response.")
            return None

        if main_tweet.startswith("MAIN_TWEET:"): main_tweet = main_tweet.replace("MAIN_TWEET:", "").strip()
        if main_tweet.startswith("Tweet:"): main_tweet = main_tweet.replace("Tweet:", "").strip()
        
        link_to_add = "\n\n🔗 outlight.fun"
        max_text_length = 280 - len(link_to_add)

        if len(main_tweet) > max_text_length:
            main_tweet = main_tweet[:max_text_length - 3] + "..."
            logging.warning(f"AI tweet truncated to {len(main_tweet)} chars to fit the link.")
        
        main_tweet += link_to_add
        
        # Logowanie sukcesu
        logging.info(f"✅ AI tweet generated successfully!")
        logging.info(f"   - Tweet: {len(main_tweet)} chars")
        
        return main_tweet
        
    except Exception as e:
        # ZMIANA: W razie błędu logujemy go i zwracamy None, zamiast używać tweeta zapasowego.
        logging.error(f"Error during AI tweet generation: {e}")
        import traceback
        logging.error(f"Full traceback: {traceback.format_exc()}")
        return None

def main():
    logging.info("GitHub Action: Bot execution started.")

    if not all([api_key, api_secret, access_token, access_token_secret]):
        logging.error("Missing required Twitter API keys. Terminating.")
        return
    
    if not openai_client:
        logging.error("❌ CRITICAL: OpenAI API key not found. Bot requires AI to function. Terminating.")
        return

    logging.info("✅ OpenAI client initialized - MONTY AI ready!")

    try:
        client = tweepy.Client(consumer_key=api_key, consumer_secret=api_secret, access_token=access_token, access_token_secret=access_token_secret)
        me = client.get_me()
        logging.info(f"Successfully authenticated as: @{me.data.username}")
        
    except Exception as e:
        logging.error(f"Error setting up Twitter client: {e}")
        return

    top_3 = get_top_tokens()
    if not top_3:
        logging.warning("No token data available. Skipping tweet for this run.")
        return

    logging.info("=== GENERATING MONTY AI TWEET ===")
    tweet_text = generate_ai_tweet(top_3)
    
    # ZMIANA: Kluczowy warunek. Jeśli tweet_text jest None (bo AI zawiodło), przerywamy.
    if not tweet_text:
        logging.error("Tweet generation failed. Nothing to send for this run.")
        logging.info("GitHub Action: Bot execution finished due to AI failure.")
        return

    # Ten kod wykona się tylko jeśli AI zadziałało i tweet_text jest poprawny.
    logging.info(f"📝 MONTY tweet prepared for sending:")
    logging.info(f"   Tweet: {len(tweet_text)} chars")
    logging.info(f"   Content: {tweet_text.replace(chr(10), ' ')}")

    try:
        logging.info("=== SENDING MONTY TWEET ===")
        main_tweet_response = safe_tweet_with_retry(client, tweet_text)
        
        if main_tweet_response:
            main_tweet_id = main_tweet_response.data['id']
            # Logowanie sukcesu wysłania
            logging.info(f"🎉 SUCCESS: MONTY AI tweet posted!")
            logging.info(f"   🔗 Tweet URL: https://x.com/{me.data.username}/status/{main_tweet_id}")
        else:
            logging.error("❌ CRITICAL ERROR: Failed to send MONTY tweet after retries!")

    except Exception as e:
        logging.error(f"Unexpected error during tweet sending process: {e}")
        import traceback
        logging.error(f"Full traceback: {traceback.format_exc()}")

    logging.info("GitHub Action: Bot execution finished.")

if __name__ == "__main__":
    main()
