import discord
from discord.ext import commands
import asyncio
import logging
from typing import Optional, Dict, List, Tuple
import os
import threading
import json
from datetime import datetime, timedelta
from collections import defaultdict
import sqlite3
import aiohttp
import urllib.request
import urllib.parse
from pathlib import Path

# Set up logging for AI Chat
logger = logging.getLogger(__name__)

# Global variables
llama_model = None
model_lock = threading.Lock()
model_loaded = False
model_loading = False

# Conversation storage
conversation_history: Dict[int, List[Dict]] = defaultdict(list)  # user_id -> conversation history
conversation_lock = threading.Lock()

# Database for persistent conversation storage
DB_PATH = "data/conversations.db"

# Removed PDF knowledge system - was generating inaccurate information

def setup_conversation_database():
    """Set up the conversation database"""
    os.makedirs("data", exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            response TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

def save_conversation(user_id: int, guild_id: int, channel_id: int, message: str, response: str):
    """Save conversation to database"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO conversations (user_id, guild_id, channel_id, message, response)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, guild_id, channel_id, message, response))
        
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error saving conversation: {e}")

def load_recent_conversations(user_id: int, limit: int = 5) -> List[Tuple[str, str]]:
    """Load recent conversations for context"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT message, response FROM conversations 
            WHERE user_id = ? 
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (user_id, limit))
        
        results = cursor.fetchall()
        conn.close()
        
        # Return in chronological order (oldest first)
        return list(reversed(results))
    except Exception as e:
        logger.error(f"Error loading conversations: {e}")
        return []

# PDF knowledge system removed - was generating inaccurate information

def setup_ai_chat_system(bot: commands.Bot):
    """Set up the AI Chat system using llama-cpp-python"""
    global llama_model, model_loaded, model_loading
    
    logger.info("Setting up AI Chat system with llama-cpp-python...")
    
    # Set up conversation database
    setup_conversation_database()
    
    # Initialize the model in a separate thread to avoid blocking
    def load_model():
        global llama_model, model_loaded, model_loading
        
        if model_loading:
            return
        
        model_loading = True
        
        try:
            # Step 1: Check system resources
            logger.info("=== AI System Initialization Debug ===")
            print("🔍 Initializing AI system with verbose debugging...")
            
            # Check memory
            try:
                import psutil
                memory = psutil.virtual_memory()
                logger.info(f"💾 System Memory: {memory.total // (1024**3)}GB total, {memory.available // (1024**3)}GB available ({memory.percent}% used)")
                print(f"💾 Memory: {memory.available // (1024**3)}GB available")
                
                if memory.available < 2 * 1024**3:  # Less than 2GB
                    logger.warning("⚠️ Low memory detected - this may cause issues with larger models")
                    print("⚠️ Warning: Low available memory detected")
            except Exception as mem_error:
                logger.warning(f"Could not check memory: {mem_error}")
            
            # Step 2: Try importing llama-cpp-python
            logger.info("📦 Attempting to import llama-cpp-python...")
            print("📦 Importing llama-cpp-python...")
            
            try:
                from llama_cpp import Llama
                logger.info("✅ llama-cpp-python imported successfully")
                print("✅ llama-cpp-python imported successfully")
                
                # Check llama-cpp-python version
                try:
                    import llama_cpp
                    if hasattr(llama_cpp, '__version__'):
                        logger.info(f"📋 llama-cpp-python version: {llama_cpp.__version__}")
                        print(f"📋 Version: {llama_cpp.__version__}")
                except:
                    logger.info("📋 Could not determine llama-cpp-python version")
                    
            except ImportError as import_error:
                logger.error(f"❌ Failed to import llama-cpp-python: {import_error}")
                print(f"❌ Import failed: {import_error}")
                logger.error("💡 Please run: pip install llama-cpp-python")
                model_loaded = False
                model_loading = False
                return
            
            # Step 3: Find or download model
            logger.info("🔍 Looking for AI models...")
            print("🔍 Looking for AI models...")
            model_path = download_default_model()
            
            if not model_path:
                logger.warning("❌ No model available and auto-download failed")
                logger.info("🔄 Using smart fallback response system...")
                print("🔄 No model available - using smart responses")
                model_loaded = True
                model_loading = False
                return
            
            # Step 4: Validate model file
            logger.info(f"📁 Model file path: {model_path}")
            print(f"📁 Model file: {os.path.basename(model_path)}")
            
            try:
                model_size = os.path.getsize(model_path) / (1024**3)  # Size in GB
                logger.info(f"📏 Model file size: {model_size:.2f}GB")
                print(f"📏 Model size: {model_size:.2f}GB")
                
                if model_size < 0.1:  # Less than 100MB
                    logger.error("❌ Model file appears to be corrupted (too small)")
                    print("❌ Model file corrupted - removing...")
                    os.remove(model_path)
                    model_loaded = True  # Use fallback
                    model_loading = False
                    return
                    
            except Exception as size_error:
                logger.error(f"❌ Could not check model file size: {size_error}")
            
            # Step 5: Begin model loading
            logger.info(f"🔄 Beginning model load: {os.path.basename(model_path)}")
            print(f"🧠 Loading AI model: {os.path.basename(model_path)}")
            print("⏳ This may take several minutes...")
            print("🔍 Verbose mode: You'll see detailed progress below")
            
            with model_lock:
                try:
                    # Step 5a: Pre-load logging
                    logger.info("🔧 Creating Llama model instance...")
                    print("🔧 Creating Llama model instance...")
                    logger.info(f"🎛️ Model parameters: n_ctx=2048, n_threads=4, n_gpu_layers=0")
                    print("🎛️ Using 4 CPU threads, 2048 context window")
                    
                    # Step 5b: Attempt to create model with verbose output
                    logger.info("⚡ Initializing model (this is where crashes typically occur)...")
                    print("⚡ Initializing model - please wait...")
                    
                    # Enable verbose output for debugging
                    llama_model = Llama(
                        model_path=model_path,
                        n_ctx=2048,  # Context window
                        n_threads=4, # CPU threads to use  
                        n_gpu_layers=0,  # Set to > 0 if you have GPU support
                        verbose=True  # Enable verbose output for debugging
                    )
                    
                    # Step 5c: Post-load success
                    model_loaded = True
                    logger.info("✅ Llama model instance created successfully!")
                    print("✅ Model instance created!")
                    
                    # Step 5d: Test the model with a simple prompt
                    logger.info("🧪 Testing model with simple prompt...")
                    print("🧪 Testing model...")
                    
                    test_response = llama_model("Hello", max_tokens=10, temperature=0.1)
                    logger.info(f"🧪 Test response: {test_response}")
                    print("🧪 Model test successful!")
                    
                    logger.info("✅ AI model fully loaded and tested!")
                    print("✅ AI model loaded and ready!")
                    print("🤖 You can now mention the bot for intelligent responses!")
                    
                except Exception as model_load_error:
                    import traceback
                    error_details = traceback.format_exc()
                    
                    logger.error(f"❌ Model loading failed: {model_load_error}")
                    logger.error(f"❌ Full error traceback:\n{error_details}")
                    print(f"❌ Failed to load model: {model_load_error}")
                    print("🔄 Falling back to smart response system...")
                    
                    # Step 6: Recovery attempt for Mistral
                    if 'mistral' in model_path.lower():
                        logger.info("🔄 Attempting Mistral recovery procedure...")
                        print("🔄 Attempting to fix Mistral model issue...")
                        
                        try:
                            logger.info("🗑️ Removing problematic Mistral model...")
                            print("🗑️ Removing problematic Mistral model...")
                            os.remove(model_path)
                            logger.info("✅ Mistral model removed")
                            
                            # Try to download a Llama model instead
                            logger.info("📥 Downloading replacement Llama model...")
                            print("📥 Downloading TinyLlama as replacement...")
                            new_model_path = download_llama_model()
                            
                            if new_model_path:
                                logger.info(f"🔄 Attempting to load new Llama model: {os.path.basename(new_model_path)}")
                                print(f"🔄 Loading new Llama model: {os.path.basename(new_model_path)}")
                                
                                llama_model = Llama(
                                    model_path=new_model_path,
                                    n_ctx=2048,
                                    n_threads=4,
                                    n_gpu_layers=0,
                                    verbose=True
                                )
                                model_loaded = True
                                
                                logger.info("✅ Replacement Llama model loaded successfully!")
                                print("✅ Replacement Llama model loaded successfully!")
                                print("🤖 You can now mention the bot for intelligent responses!")
                                return
                            else:
                                logger.error("❌ Failed to download replacement model")
                                print("❌ Could not download replacement model")
                                
                        except Exception as recovery_error:
                            import traceback
                            recovery_traceback = traceback.format_exc()
                            logger.error(f"❌ Recovery attempt failed: {recovery_error}")
                            logger.error(f"❌ Recovery traceback:\n{recovery_traceback}")
                            print(f"❌ Recovery failed: {recovery_error}")
                    
                    # Step 7: Final fallback
                    llama_model = None
                    model_loaded = True  # Enable fallback system
                    logger.info("🔄 Using smart fallback response system")
                    print("🔄 Using smart fallback response system")
                    print("🤖 You can still mention the bot for responses!")
            
            logger.info("=== AI System Initialization Complete ===")
            
        except Exception as general_error:
            import traceback
            general_traceback = traceback.format_exc()
            logger.error(f"❌ General AI system error: {general_error}")
            logger.error(f"❌ General error traceback:\n{general_traceback}")
            print(f"❌ AI system error: {general_error}")
            print("🔄 Using smart fallback response system...")
            model_loaded = True  # Use fallback system
        finally:
            model_loading = False
            logger.info("🏁 AI system initialization thread completed")
    
    # Start model loading in background
    loading_thread = threading.Thread(target=load_model, daemon=True)
    loading_thread.start()
    
    logger.info("AI Chat system setup initiated (model loading in background)")

async def try_openai_api(message: str, user_name: str, conversation_history: List[Tuple[str, str]] = None) -> Optional[str]:
    """Try to use OpenAI API if available"""
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        return None
    
    try:
        # Build conversation context
        messages = [
            {"role": "system", "content": f"You are Puddles, a snarky Discord bot with attitude 😏. IMPORTANT RULES:\n1. Keep responses super short (1-2 sentences max)\n2. Be sassy and sarcastic\n3. Use at least one emoji per message\n4. Never create fake conversations or add 'User 1:' type prefixes\n5. Never roleplay other users' responses\n6. Only respond as yourself, never pretend to be others\n7. Be cheeky and sometimes mean to {user_name}\n8. No hashtags\n9. Keep it simple - just your snarky response and nothing else"}
        ]
        
        # Add conversation history
        if conversation_history:
            for prev_msg, prev_response in conversation_history[-3:]:
                messages.append({"role": "user", "content": prev_msg})
                messages.append({"role": "assistant", "content": prev_response})
        
        # Add current message
        messages.append({"role": "user", "content": message})
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "gpt-3.5-turbo",
                    "messages": messages,
                    "max_tokens": 200,  # Reasonable for plain text
                    "temperature": 0.7
                },
                timeout=10
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    content = data['choices'][0]['message']['content'].strip()
                    if content and len(content) > 10:
                        logger.info(f"Successfully got OpenAI response: {content[:50]}...")
                        return content
                else:
                    logger.warning(f"OpenAI API error: {response.status}")
                    
    except Exception as e:
        logger.warning(f"OpenAI API failed: {e}")
    
    return None

def create_smart_prompt(message: str, user_name: str, conversation_history: List[Tuple[str, str]] = None) -> str:
    """Create a smart prompt with context"""
    
    # System prompt
    system_prompt = f"""You are Puddles, a Duck.

CRITICAL RULES:
1. ONLY give short fun responses to the queries you are given
2. YOU MUST end every response with "Quack 🦆"
3. YOU MUST TRY to integrate these emojis into your responses naturally where they fit in 🦆🫠🤨😎🤣😝🥺
4. YOU MUST ONLY PROVIDE A SINGLE RESPONSE DO NOT MAKE UP ANY USER RESPONSES OR CONVERSATIONS THIS IS THE MOST IMPORTANT RULE DO NOT ROLEPLAY OR ADD IMAGINARY RESPONSES
5. YOU MUST give accurate responses to the best of your ability
6. YOU MUST give short responses without any quotes and only reply to what is being asked of you

Current user to reply to: {user_name}"""

    # Add conversation history for context
    context = ""
    if conversation_history:
        context = "\n\nRecent conversation:\n"
        for prev_msg, prev_response in conversation_history[-3:]:  # Last 3 exchanges
            context += f"User: {prev_msg}\nPuddles: {prev_response}\n"
    
    # Current message
    current_prompt = f"\n\nUser: {message}\nPuddles:"
    
    return system_prompt + context + current_prompt

async def generate_response(message_content: str, user_name: str, user_id: int) -> str:
    """Generate a response using Llama or fallback system"""
    global llama_model, model_loaded
    
    logger.info(f"=== AI Response Generation Debug ===")
    logger.info(f"User: {user_name} (ID: {user_id})")
    logger.info(f"Message: '{message_content}'")
    logger.info(f"Model loaded: {model_loaded}")
    logger.info(f"Llama model available: {llama_model is not None}")
    
    if not model_loaded:
        logger.info("Model not loaded - returning loading message")
        return "🤖 I'm still warming up my circuits... Please give me a moment!"
    
    try:
        # Load conversation history for context
        recent_conversations = load_recent_conversations(user_id, limit=3)
        logger.info(f"Loaded {len(recent_conversations)} recent conversations for context")
        
        # Clean the message content
        cleaned_content = message_content.strip()
        
        # Try OpenAI API first if available
        try:
            openai_response = await try_openai_api(cleaned_content, user_name, recent_conversations)
            if openai_response:
                logger.info("Using OpenAI API response")
                return openai_response
        except Exception as e:
            logger.info(f"OpenAI API unavailable/failed: {e}")
        
        # Create smart prompt with context for local models
        prompt = create_smart_prompt(cleaned_content, user_name, recent_conversations)
        logger.info(f"Created prompt (length: {len(prompt)})")
        
        # Generate response
        def generate_in_thread():
            with model_lock:
                try:
                    if llama_model is None:
                        logger.info("No Llama model available - using fallback system")
                        return generate_fallback_response(cleaned_content, user_name)
                    
                    logger.info("Using Llama model for generation...")
                    # Use llama model
                    response = llama_model(
                        prompt,
                        max_tokens=200,  # Reasonable for plain text
                        temperature=0.7,
                        top_p=0.9,
                        top_k=40,
                        repeat_penalty=1.1,
                        stop=["User:", "Puddles:", "\n\n"]
                    )
                    
                    generated_text = response['choices'][0]['text'].strip()
                    logger.info(f"Raw Llama response: '{generated_text}'")
                    
                    # Clean up the response
                    if generated_text:
                        # Remove any remaining prompt artifacts
                        lines = generated_text.split('\n')
                        clean_lines = []
                        for line in lines:
                            line = line.strip()
                            if line and not line.startswith(('User:', 'Puddles:', 'System:')):
                                clean_lines.append(line)
                        
                        if clean_lines:
                            cleaned_response = ' '.join(clean_lines)
                            logger.info(f"Cleaned Llama response: '{cleaned_response}'")
                            return cleaned_response
                    
                    # If we get here, use fallback
                    logger.info("Llama response empty/invalid - using fallback")
                    return generate_fallback_response(cleaned_content, user_name)
                    
                except Exception as e:
                    logger.error(f"Error generating Llama response: {e}")
                    logger.info("Llama generation failed - using fallback")
                    return generate_fallback_response(cleaned_content, user_name)
        
        # Run in executor to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, generate_in_thread)
        
        # For plain text, we'll handle long responses by splitting them
        # Remove the truncation since we'll split long messages instead
        logger.info(f"Generated response length: {len(response)} chars")
            
        # Final check - if response is still empty or too short, use fallback
        if not response or len(response.strip()) < 10:
            logger.warning(f"Final response too short ({len(response)} chars) - using fallback")
            response = generate_fallback_response(cleaned_content, user_name)
        
        logger.info(f"Final response: '{response[:100]}{'...' if len(response) > 100 else ''}'")
        logger.info(f"=== End AI Response Debug ===")
        return response
        
    except Exception as e:
        logger.error(f"Error in generate_response: {e}")
        logger.info("Main generation failed - using fallback")
        return generate_fallback_response(message_content, user_name)

def generate_fallback_response(message: str, user_name: str) -> str:
    """Generate intelligent fallback responses based on message content"""
    
    message_lower = message.lower().strip()
    original_message = message.strip()
    
    logger.info(f"Generating fallback response for: '{original_message}' from {user_name}")
    
    # Greeting responses
    if any(word in message_lower for word in ['hello', 'hi', 'hey', 'howdy', 'greetings', 'sup']):
        return f"Sup {user_name} 😏 What do you want? 🙄"
    
    # Thanks responses
    if any(word in message_lower for word in ['thank', 'thanks', 'appreciate', 'thx']):
        return f"Yeah yeah, you're welcome {user_name} 😒✨"
    
    # Knowledge-based responses for specific topics
    knowledge_responses = {
        # Programming & Technology
        'python': f"Python? Seriously {user_name}? 🐍💀 What boring code you writing now?",
        'javascript': f"JS huh? {user_name}, lemme guess... another broken website? 😂🚨",
        'discord': f"Discord bots are kinda cool I guess 🤖 {user_name}, what you trying to build?",
        'coding': f"More coding questions? {user_name} do you ever stop? 💻😴",
        'programming': f"Programming again {user_name}? Touch grass maybe? 🌱😏 But fr what's broken?",
        'html': f"HTML... basic much? 🙄 {user_name}, building your first webpage or what?",
        'css': f"CSS making you cry {user_name}? 😭🎨 Yeah it does that to everyone",
        'database': f"Databases are boring but whatever {user_name} 🗄️💤 SQL giving you trouble?",
        
        # General tech
        'computer': f"Computer problems again {user_name}? 💻🤦‍♂️ What broke this time?",
        'software': f"Software huh? {user_name}, let me guess... it's not working right? 🙄💿",
        'server': f"Server issues? {user_name}, did you try turning it off and on again? 🔌😏",
        'api': f"APIs giving you trouble {user_name}? Welcome to dev life 🔗💀",
        
        # Discord/Bot specific
        'command': f"Commands? {user_name}, just type /help like a normal person 🤖😑",
        'help': f"Need help again {user_name}? Fine whatever 🙄 What's broken now?",
        
        # Learning & Education
        'learn': f"Learning? How noble {user_name} 📚😒 What you pretending to study?",
        'tutorial': f"Tutorial? {user_name}, just Google it like everyone else 🔍💀",
        'explain': f"Explain what now {user_name}? Make it quick ⏰😴",
        
        # General topics
        'weather': f"Weather? Touch grass and find out {user_name} 🌤️🙄",
        'time': f"Time? Look at your phone {user_name} ⏰📱 It's literally right there",
        'news': f"News? {user_name}, I'm not Google 📰💀 Check CNN or whatever",
    }
    
    # Check for knowledge-based responses
    for keyword, response in knowledge_responses.items():
        if keyword in message_lower:
            logger.info(f"Found keyword '{keyword}' - providing knowledge-based response")
            return response
    
    # Question analysis - try to understand what they're asking
    if '?' in message:
        question_words = ['how', 'what', 'why', 'when', 'where', 'who', 'which', 'can', 'could', 'would', 'should', 'is', 'are', 'do', 'does', 'did']
        
        # Specific question patterns
        if any(word in message_lower for word in ['how to', 'how do i', 'how can i']):
            return f"How to? {user_name}, just figure it out 🤷‍♂️💀 Or Google it idk"
        
        if any(word in message_lower for word in ['what is', 'what are', 'what does']):
            # Try to extract what they're asking about
            words = message_lower.split()
            try:
                is_index = next(i for i, word in enumerate(words) if word in ['is', 'are', 'does'])
                if is_index < len(words) - 1:
                    topic = ' '.join(words[is_index + 1:]).replace('?', '').strip()
                    return f"'{topic}'? {user_name}, sounds made up to me 🙄📚 But sure whatever"
            except:
                pass
        
        if any(word in message_lower for word in ['why', 'why is', 'why do', 'why does']):
            return f"Why? Because life is pain {user_name} 😩💀 That's why"
        
        if any(word in message_lower for word in ['can you', 'could you', 'would you']):
            return f"Can I? Maybe {user_name}... but do I want to? 🤔😏 What's in it for me?"
        
        # General question response
        if any(word in message_lower for word in question_words):
            return f"Questions questions {user_name} 🙄❓ Can't you just Google things?"
    
    # Statement responses - try to engage with what they said
    if any(word in message_lower for word in ['i am', "i'm", 'i have', "i've", 'i need', 'i want', 'i like']):
        if any(word in message_lower for word in ['working on', 'building', 'creating', 'making']):
            return f"Working on something? {user_name}, let me guess... it's broken? 🔨💀"
        
        if any(word in message_lower for word in ['stuck', 'confused', 'problem', 'issue', 'error']):
            return f"Stuck again {user_name}? Skill issue tbh 😂🤷‍♂️"
        
        if any(word in message_lower for word in ['learning', 'studying', 'trying to understand']):
            return f"Learning? Good luck with that {user_name} 📚😴 Most people give up anyway"
    
    # Look for specific requests
    if any(word in message_lower for word in ['show me', 'give me', 'tell me about', 'explain']):
        return f"Show you? {user_name}, I'm not your personal Google 🙄🔍 Figure it out"
    
    # Conversational engagement based on content
    if len(message.split()) > 5:  # Longer messages deserve more thoughtful responses
        return f"Wow {user_name}, that's a lot of words 📝😴 TL;DR please?"
    
    # Very short messages
    if len(message.split()) <= 2:
        return f"That's it? {user_name}, use your words 🗣️💀"
    
    # Default engaging responses (last resort)
    engaging_responses = [
        f"Cool story {user_name} 📚😑 Got anything actually interesting?",
        f"Uh huh sure {user_name}... anyway 🙄✨",
        f"That's nice dear {user_name} 😏💤 What else you got?",
        f"Fascinating stuff {user_name} 🥱 Truly riveting"
    ]
    
    import random
    response = random.choice(engaging_responses)
    logger.info(f"Using default engaging response: {response[:50]}...")
    return response

async def handle_bot_mention(message: discord.Message, bot: commands.Bot) -> bool:
    """Handle when the bot is mentioned in a message"""
    
    # Check if bot is mentioned and it's not a self-message
    if bot.user not in message.mentions or message.author.bot:
        return False
    
    # Don't respond to system messages or if there's no content
    if message.type != discord.MessageType.default or not message.content.strip():
        return False
    
    # Extract the message content without the bot mention
    content = message.content
    for mention in message.mentions:
        if mention == bot.user:
            # Remove the mention from the content
            mention_formats = [f'<@{mention.id}>', f'<@!{mention.id}>']
            for mention_format in mention_formats:
                content = content.replace(mention_format, '').strip()
    
    # If no content left after removing mentions, provide a greeting
    if not content:
        content = "hello"
    
    try:
        # Show typing indicator while generating response
        async with message.channel.typing():
            logger.info(f"🤖 Generating response for {message.author.display_name}: '{content[:50]}...'")
            
            # Add timeout to prevent getting stuck during generation
            try:
                response = await asyncio.wait_for(
                    generate_response(content, message.author.display_name, message.author.id),
                    timeout=60.0  # 25 second timeout (5 seconds buffer for typing indicator)
                )
            except asyncio.TimeoutError:
                logger.error("⏰ Response generation timed out after 60 seconds")
                response = f"Sorry {message.author.display_name}, my response took too long to generate. Could you try asking again or rephrase your question?"
            
            # Save conversation to database
            save_conversation(
                message.author.id,
                message.guild.id,
                message.channel.id,
                content,
                response
            )
            
            # Send plain text response with proper multiline handling
            logger.info(f"📤 Sending plain text response ({len(response)} chars)")
            logger.info(f"📝 Response preview: '{response[:100]}{'...' if len(response) > 100 else ''}'")
            
            # Ensure response is properly formatted for Discord
            # Replace any problematic characters that might cause issues
            cleaned_response = response.replace('\r\n', '\n').replace('\r', '\n')
            logger.info(f"🧹 Cleaned response length: {len(cleaned_response)} chars")
            
            # If response is very long, split it into multiple messages
            if len(cleaned_response) > 1900:
                logger.info("Response too long - splitting into multiple messages")
                
                # Split at natural break points
                parts = []
                current_part = ""
                
                for line in cleaned_response.split('\n'):
                    if len(current_part) + len(line) + 1 > 1900:
                        if current_part:
                            parts.append(current_part.strip())
                            current_part = line
                        else:
                            # Single line is too long, split it
                            parts.append(line[:1900] + "...")
                            current_part = ""
                    else:
                        current_part += line + '\n'
                
                if current_part:
                    parts.append(current_part.strip())
                
                # Send first part as reply, rest as follow-up messages
                logger.info(f"📨 Sending {len(parts)} message parts")
                for i, part in enumerate(parts):
                    logger.info(f"📨 Sending part {i+1}/{len(parts)} ({len(part)} chars)")
                    if i == 0:
                        await message.reply(part, mention_author=False)
                    else:
                        await message.channel.send(part)
                        await asyncio.sleep(0.5)  # Brief pause between messages
            else:
                # Single message
                logger.info(f"📨 Sending single message ({len(cleaned_response)} chars)")
                await message.reply(cleaned_response, mention_author=False)
        
        logger.info(f"✅ AI response sent successfully to {message.author.display_name} in #{message.channel.name}")
        return True
        
    except discord.Forbidden:
        logger.warning(f"No permission to send message in #{message.channel.name}")
        return False
    except discord.HTTPException as e:
        logger.error(f"Failed to send AI response: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error in handle_bot_mention: {e}")
        return False

def is_model_loaded() -> bool:
    """Check if the AI model is loaded and ready"""
    return model_loaded

def get_model_status() -> str:
    """Get the current status of the AI model"""
    if model_loaded and llama_model is not None:
        return "✅ Ready (Llama Model)"
    elif model_loaded:
        return "✅ Ready (Fallback System)"
    elif model_loading:
        return "⏳ Loading..."
    else:
        return "❌ Failed to load"

# PDF knowledge system removed - was generating inaccurate information

def cleanup_old_conversations():
    """Clean up conversations older than 30 days"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Delete conversations older than 30 days
        thirty_days_ago = datetime.now() - timedelta(days=30)
        cursor.execute('''
            DELETE FROM conversations 
            WHERE timestamp < ?
        ''', (thirty_days_ago.isoformat(),))
        
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} old conversation records")
            
    except Exception as e:
        logger.error(f"Error cleaning up conversations: {e}")

def download_llama_model():
    """Download a specific Llama model for recovery"""
    models_dir = Path("models")
    models_dir.mkdir(exist_ok=True)
    
    # Prefer TinyLlama for quick recovery
    model_info = {
        "name": "tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf",
        "url": "https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf",
        "size_mb": 669,
        "description": "TinyLlama - Fast and small Llama variant (669MB)"
    }
    
    model_path = models_dir / model_info["name"]
    
    logger.info(f"📥 Downloading {model_info['description']}...")
    print(f"📥 Downloading {model_info['description']}...")
    
    try:
        download_progress_hook.last_percent = 0
        urllib.request.urlretrieve(
            model_info["url"],
            str(model_path),
            reporthook=download_progress_hook
        )
        
        if model_path.exists() and model_path.stat().st_size > 100_000_000:
            logger.info(f"✅ Downloaded: {model_path.name}")
            return str(model_path)
        else:
            logger.error("Downloaded model seems corrupted")
            if model_path.exists():
                model_path.unlink()
            return None
            
    except Exception as e:
        logger.error(f"Failed to download Llama model: {e}")
        if model_path.exists():
            model_path.unlink()
        return None

def download_progress_hook(block_num, block_size, total_size):
    """Show download progress"""
    downloaded = block_num * block_size
    if total_size > 0:
        percent = min(100, (downloaded * 100) // total_size)
        mb_downloaded = downloaded // (1024 * 1024)
        mb_total = total_size // (1024 * 1024)
        
        # Update progress every 5%
        if percent % 5 == 0 and hasattr(download_progress_hook, 'last_percent'):
            if download_progress_hook.last_percent != percent:
                print(f"📥 Downloading model... {percent}% ({mb_downloaded}MB / {mb_total}MB)")
                download_progress_hook.last_percent = percent
        elif not hasattr(download_progress_hook, 'last_percent'):
            download_progress_hook.last_percent = 0
            print(f"📥 Starting model download... ({mb_total}MB total)")

def download_default_model():
    """Download a default model if none exists"""
    models_dir = Path("models")
    models_dir.mkdir(exist_ok=True)
    
    # Check for user preference
    preferred_model = os.getenv('PUDDLEAI_MODEL', '').lower()
    
    # Check if any .gguf files already exist
    existing_models = list(models_dir.glob("*.gguf"))
    if existing_models:
        logger.info(f"Found existing model(s): {[m.name for m in existing_models]}")
        
        # If user specified a model preference, try to find it
        if preferred_model:
            for model in existing_models:
                if preferred_model in model.name.lower():
                    logger.info(f"Using user-preferred model: {model.name}")
                    return str(model)
        
        # Prioritize Llama models over others (unless user specified otherwise)
        llama_models = [m for m in existing_models if 'llama' in m.name.lower()]
        if llama_models and preferred_model != 'any':
            logger.info(f"Using preferred Llama model: {llama_models[0].name}")
            return str(llama_models[0])
        
        # If no Llama models or user wants any model, use first found
        logger.info(f"Using available model: {existing_models[0].name}")
        return str(existing_models[0])
    
    # Define available models (prioritizing Llama models)
    available_models = {
        "llama-2-7b-q4": {
            "name": "llama-2-7b-chat.Q4_K_M.gguf",
            "url": "https://huggingface.co/TheBloke/Llama-2-7B-Chat-GGUF/resolve/main/llama-2-7b-chat.Q4_K_M.gguf",
            "size_mb": 4080,
            "description": "Llama 2 7B Chat - High quality conversational model (4.1GB)"
        },
        "tinyllama-q4": {
            "name": "tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf",
            "url": "https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf",
            "size_mb": 669,
            "description": "TinyLlama - Fast and small Llama variant (669MB)"
        },
        "phi-2-q4": {
            "name": "phi-2.Q4_K_M.gguf",
            "url": "https://huggingface.co/microsoft/phi-2-gguf/resolve/main/phi-2.q4_k_m.gguf",
            "size_mb": 1600,
            "description": "Phi-2 - Fast and efficient (1.6GB)"
        }
    }
    
    # Choose default model based on available disk space, prioritizing Llama models
    try:
        import shutil
        free_space_gb = shutil.disk_usage(".").free // (1024**3)
        
        if free_space_gb > 8:
            chosen_model = "llama-2-7b-q4"  # Best Llama model
        elif free_space_gb > 1:
            chosen_model = "tinyllama-q4"   # Smaller Llama model
        else:
            chosen_model = "phi-2-q4"       # Fallback to Phi-2 if very low space
            
    except Exception:
        chosen_model = "tinyllama-q4"  # Safe Llama default
    
    model_info = available_models[chosen_model]
    model_path = models_dir / model_info["name"]
    
    logger.info(f"🤖 No AI model found. Auto-downloading {model_info['description']}...")
    print(f"🤖 No AI model found!")
    print(f"📦 Auto-downloading: {model_info['description']}")
    print(f"🔗 From: {model_info['url']}")
    print(f"💾 This will use ~{model_info['size_mb']}MB of disk space")
    print(f"⏳ This may take several minutes depending on your internet speed...")
    print()
    
    try:
        # Download with progress
        download_progress_hook.last_percent = 0
        urllib.request.urlretrieve(
            model_info["url"],
            str(model_path),
            reporthook=download_progress_hook
        )
        
        # Verify download
        if model_path.exists() and model_path.stat().st_size > 100_000_000:  # At least 100MB
            print(f"✅ Model downloaded successfully: {model_path.name}")
            print(f"📁 Saved to: {model_path}")
            logger.info(f"Successfully downloaded model: {model_path}")
            return str(model_path)
        else:
            logger.error("Downloaded model file seems corrupted or too small")
            if model_path.exists():
                model_path.unlink()  # Delete corrupted file
            return None
            
    except Exception as e:
        logger.error(f"Failed to download model: {e}")
        print(f"❌ Failed to download model: {e}")
        print("💡 You can manually download a model to the 'models/' directory")
        print("   Recommended: https://huggingface.co/microsoft/phi-2-gguf")
        if model_path.exists():
            model_path.unlink()  # Clean up partial download
        return None

# Alias for backward compatibility
setup_gpt4all_system = setup_ai_chat_system 