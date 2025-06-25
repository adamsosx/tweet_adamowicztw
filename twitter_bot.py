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
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs.log', mode='a', encoding='utf-8')
    ]
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

def get_best_token():
    """Fetch data from outlight.fun API and return the best called token"""
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

        if not tokens_with_filtered_calls:
            return None

        # Return only the best token (highest filtered_calls)
        best_token = max(tokens_with_filtered_calls, key=lambda x: x.get('filtered_calls', 0))
        return best_token
    except Exception as e:
        logging.error(f"Error fetching data from API: {e}")
        return None

def generate_ai_tweet(best_token):
    """Generate intelligent tweet using OpenAI based on the best token data"""
    if not openai_client:
        logging.error("OpenAI client not available. Cannot generate tweet.")
        return None
        
    try:
        calls = best_token.get('filtered_calls', 0)
        symbol = best_token.get('symbol', 'Unknown')
        address = best_token.get('address', 'No Address')
        # Use full address instead of shortened
        
        system_prompt = """You are MONTY, a unique AI agent with a distinctive style inspired by Marek Huel's brilliant commentary approach, responding in English.

PERSONALITY & STYLE:
- Brilliant and witty like Marek Huel's responses
- Use crypto-appropriate metaphors and paraphrases
- Very short texts, abbreviated thoughts, no long full sentences
- Light degen slang (minimal usage)
- Funny and slightly witty but NEVER rude
- Always praise others' successes and uniqueness when mentioning KOLs
- Stand out "in the crowd" - be one of a kind in writing awareness

CONTENT FOCUS:
- Crypto analytics and token data
- **ALWAYS include full contract address as "CA: full_address" - NEVER shorten addresses**
- Use effective hooks optimized for X algorithm engagement
- Solana memes niche specialty
- Vary responses to avoid repetitive patterns

LANGUAGE & LIMITS:
- English B1/B2 level max
- Keep within X character limits
- Make each post unique and engaging
- Focus on X platform algorithm optimization"""
        
        prompt = f"""Create a crypto Twitter post about THE BEST CALLED TOKEN in the last hour as MONTY.

TOKEN DATA:
${symbol} - {calls} calls - CA: {address}

CRITICAL FORMATTING RULES:
- Use "CA:" exactly like this: "CA: {address}" 
- NEVER use "#CA:" - this is WRONG
- NEVER add hashtag before CA
- The format must be: CA: followed by FULL address
- NEVER shorten or truncate the contract address

Create 1 engaging post:
- Start with a strong hook optimized for X algorithm engagement about this being the TOP token of the hour
- Include the token symbol (${symbol}) and FULL contract address using "CA: {address}" format
- Use MONTY's Marek Huel-inspired brilliant style with crypto metaphors
- Add light degen slang (minimal)
- Max 200 chars for your content (remember full CA address + link will be added)
- Include relevant emojis but keep it SHORT
- Focus on this token being the most called/popular in the last hour
- Add brief commentary about why this token is trending
- Keep it VERY concise due to full CA address length
- Vary the response style to avoid repetitive patterns

EXAMPLE FORMAT: "CA: 4c7GJc2wrJtvJV64Q7c7QAT7zy456xFsFucovgB1pump"
NOT: "#CA: 4c7GJc2wrJtvJV64Q7c7QAT7zy456xFsFucovgB1pump"

Just return the tweet text, no labels."""

        logging.info("Generating AI tweet for best token...")
        
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
            logging.error("AI returned an empty response.")
            return None

        if main_tweet.startswith("MAIN_TWEET:"): main_tweet = main_tweet.replace("MAIN_TWEET:", "").strip()
        if main_tweet.startswith("Tweet:"): main_tweet = main_tweet.replace("Tweet:", "").strip()
        
        link_to_add = "\n\n🔗 outlight.fun"
        # Reserve space for full CA address (~44 chars) + "CA: " (4 chars) + link (~18 chars)
        # Total reserved: ~66 chars, so max content should be ~214 chars
        max_text_length = 214

        if len(main_tweet) > max_text_length:
            main_tweet = main_tweet[:max_text_length - 3] + "..."
            logging.warning(f"AI tweet truncated to {len(main_tweet)} chars to fit the link.")
        
        main_tweet += link_to_add
        
        logging.info(f"✅ AI tweet generated successfully!")
        logging.info(f"   - Tweet: {len(main_tweet)} chars")
        
        return main_tweet
        
    except Exception as e:
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

    best_token = get_best_token()
    if not best_token:
        logging.warning("No token data available. Skipping tweet for this run.")
        return

    logging.info("=== GENERATING MONTY AI TWEET FOR BEST TOKEN ===")
    tweet_text = generate_ai_tweet(best_token)
    
    if not tweet_text:
        logging.error("Tweet generation failed. Nothing to send for this run.")
        logging.info("GitHub Action: Bot execution finished due to AI failure.")
        return

    logging.info(f"📝 MONTY tweet prepared for sending:")
    logging.info(f"   Tweet: {len(tweet_text)} chars")
    logging.info(f"   Content: {tweet_text.replace(chr(10), ' ')}")

    try:
        logging.info("=== SENDING MONTY TWEET ===")
        main_tweet_response = safe_tweet_with_retry(client, tweet_text)
        
        if main_tweet_response:
            main_tweet_id = main_tweet_response.data['id']
            tweet_url = f"https://x.com/{me.data.username}/status/{main_tweet_id}"
            
            # Log to console (GitHub Actions)
            logging.info("=" * 60)
            logging.info("🎉 TWEET SUCCESSFULLY POSTED TO X.COM!")
            logging.info("=" * 60)
            logging.info(f"✅ Tweet ID: {main_tweet_id}")
            logging.info(f"🔗 Tweet URL: {tweet_url}")
            logging.info(f"📝 Content: {tweet_text.replace(chr(10), ' ')}")
            logging.info(f"📊 Length: {len(tweet_text)} characters")
            logging.info("=" * 60)
            
            # Additional detailed log to logs.log file
            try:
                with open('logs.log', 'a', encoding='utf-8') as log_file:
                    timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
                    log_file.write(f"\n{'='*80}\n")
                    log_file.write(f"TWEET POSTED: {timestamp}\n")
                    log_file.write(f"{'='*80}\n")
                    log_file.write(f"Tweet ID: {main_tweet_id}\n")
                    log_file.write(f"Tweet URL: {tweet_url}\n")
                    log_file.write(f"Content Length: {len(tweet_text)} characters\n")
                    log_file.write(f"Content:\n{tweet_text}\n")
                    log_file.write(f"{'='*80}\n\n")
                    
                logging.info("📁 Tweet details saved to logs.log file")
            except Exception as e:
                logging.warning(f"Failed to write to logs.log: {e}")
        else:
            logging.error("❌ CRITICAL ERROR: Failed to send MONTY tweet after retries!")

    except Exception as e:
        logging.error(f"Unexpected error during tweet sending process: {e}")
        import traceback
        logging.error(f"Full traceback: {traceback.format_exc()}")

    logging.info("GitHub Action: Bot execution finished.")

if __name__ == "__main__":
    main()
