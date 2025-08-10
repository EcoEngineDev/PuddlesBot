import discord
from discord.ext import commands
import asyncio
import logging
from typing import Optional
import os
import threading
from pathlib import Path
import disable  # Add this to imports

# Set up logging for AI Chat
logger = logging.getLogger(__name__)

# Global variables
mistral_model = None
model_lock = threading.Lock()
model_loaded = False
model_loading = False

def setup_ai_chat_system(bot: commands.Bot):
    """Set up the AI Chat system using Mistral 7B"""
    global mistral_model, model_loaded, model_loading
    
    logger.info("Setting up AI Chat system with Mistral 7B...")
    
    # Initialize the model in a separate thread to avoid blocking
    def load_model():
        global mistral_model, model_loaded, model_loading
        
        if model_loading:
            return
        
        model_loading = True
        
        try:
            # Step 1: Check system resources
            logger.info("=== AI System Initialization Debug ===")
            print("🔍 Initializing AI system with Mistral 7B...")
            
            # Check memory
            try:
                import psutil
                memory = psutil.virtual_memory()
                logger.info(f"💾 System Memory: {memory.total // (1024**3)}GB total, {memory.available // (1024**3)}GB available ({memory.percent}% used)")
                print(f"💾 Memory: {memory.available // (1024**3)}GB available")
                
                if memory.available < 4 * 1024**3:  # Less than 4GB
                    logger.warning("⚠️ Low memory detected - Mistral 7B requires at least 4GB RAM")
                    print("⚠️ Warning: Low available memory detected for Mistral 7B")
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
            
            # Step 3: Find or download Mistral 7B model
            logger.info("🔍 Looking for Mistral 7B model...")
            print("🔍 Looking for Mistral 7B model...")
            model_path = download_mistral_model()
            
            if not model_path:
                logger.warning("❌ No Mistral 7B model available and auto-download failed")
                logger.info("🔄 Using smart fallback response system...")
                print("🔄 No Mistral 7B available - using smart responses")
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
                
                if model_size < 3.0:  # Less than 3GB (Mistral 7B should be ~4GB)
                    logger.error("❌ Model file appears to be corrupted (too small for Mistral 7B)")
                    print("❌ Model file corrupted - removing...")
                    os.remove(model_path)
                    model_loaded = True  # Use fallback
                    model_loading = False
                    return
                    
            except Exception as size_error:
                logger.error(f"❌ Could not check model file size: {size_error}")
            
            # Step 5: Begin model loading
            logger.info(f"🔄 Beginning Mistral 7B model load: {os.path.basename(model_path)}")
            print(f"🧠 Loading Mistral 7B model: {os.path.basename(model_path)}")
            print("⏳ This may take several minutes...")
            print("🔍 Verbose mode: You'll see detailed progress below")
            
            with model_lock:
                try:
                    # Step 5a: Pre-load logging
                    logger.info("🔧 Creating Mistral model instance...")
                    print("🔧 Creating Mistral model instance...")
                    logger.info(f"🎛️ Model parameters: n_ctx=4096, n_threads=8, n_gpu_layers=0")
                    print("🎛️ Using 8 CPU threads, 4096 context window")
                    
                    # Step 5b: Attempt to create model with verbose output
                    logger.info("⚡ Initializing Mistral 7B model (this is where crashes typically occur)...")
                    print("⚡ Initializing Mistral 7B model - please wait...")
                    
                    # Enable verbose output for debugging
                    mistral_model = Llama(
                        model_path=model_path,
                        n_ctx=4096,  # Larger context window for Mistral
                        n_threads=8,  # More threads for better performance
                        n_gpu_layers=0,  # Set to > 0 if you have GPU support
                        verbose=True  # Enable verbose output for debugging
                    )
                    
                    # Step 5c: Post-load success
                    model_loaded = True
                    logger.info("✅ Mistral 7B model instance created successfully!")
                    print("✅ Mistral 7B model instance created!")
                    
                    # Step 5d: Test the model with a simple prompt
                    logger.info("🧪 Testing Mistral 7B model with simple prompt...")
                    print("🧪 Testing Mistral 7B model...")
                    
                    test_response = mistral_model("Hello", max_tokens=10, temperature=0.1)
                    logger.info(f"🧪 Test response: {test_response}")
                    print("🧪 Mistral 7B model test successful!")
                    
                    logger.info("✅ Mistral 7B AI model fully loaded and tested!")
                    print("✅ Mistral 7B AI model loaded and ready!")
                    print("🤖 You can now mention the bot for intelligent responses!")
                    
                except Exception as model_load_error:
                    import traceback
                    error_details = traceback.format_exc()
                    
                    logger.error(f"❌ Mistral 7B model loading failed: {model_load_error}")
                    logger.error(f"❌ Full error traceback:\n{error_details}")
                    print(f"❌ Failed to load Mistral 7B model: {model_load_error}")
                    print("🔄 Falling back to smart response system...")
                    
                    # Final fallback
                    mistral_model = None
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
    
    logger.info("AI Chat system setup initiated (Mistral 7B model loading in background)")

def create_mistral_prompt(message: str, user_name: str) -> str:
    """Create a prompt optimized for Mistral 7B"""
    
    system_prompt = f"""<s>[INST] You are Puddles, a Duck.

CRITICAL RULES:
1. ONLY give short fun responses to the queries you are given
2. YOU MUST end every response with "Quack 🦆"
3. YOU MUST TRY to integrate these emojis into your responses naturally where they fit in 🦆🫠🤨😎🤣😝🥺
4. YOU MUST ONLY PROVIDE A SINGLE RESPONSE DO NOT MAKE UP ANY USER RESPONSES OR CONVERSATIONS THIS IS THE MOST IMPORTANT RULE DO NOT ROLEPLAY OR ADD IMAGINARY RESPONSES
5. YOU MUST give accurate responses to the best of your ability
6. YOU MUST give short responses without any quotes and only reply to what is being asked of you
7. YOU MUST reply in the language that the user is speaking - detect their language and respond accordingly

Current user to reply to: {user_name}

User: {message} [/INST]"""
    
    return system_prompt

async def generate_response(message_content: str, user_name: str, user_id: int) -> str:
    """Generate a response using Mistral 7B or fallback system"""
    global mistral_model, model_loaded
    
    logger.info(f"=== AI Response Generation Debug ===")
    logger.info(f"User: {user_name} (ID: {user_id})")
    logger.info(f"Message: '{message_content}'")
    logger.info(f"Model loaded: {model_loaded}")
    logger.info(f"Mistral model available: {mistral_model is not None}")
    
    if not model_loaded:
        logger.info("Model not loaded - returning loading message")
        return "🤖 I'm still warming up my circuits... Please give me a moment!"
    
    try:
        # Clean the message content
        cleaned_content = message_content.strip()
        
        # Create Mistral-optimized prompt
        prompt = create_mistral_prompt(cleaned_content, user_name)
        logger.info(f"Created Mistral prompt (length: {len(prompt)})")
        
        # Generate response
        def generate_in_thread():
            with model_lock:
                try:
                    if mistral_model is None:
                        logger.info("No Mistral model available - using fallback system")
                        return generate_fallback_response(cleaned_content, user_name)
                    
                    logger.info("Using Mistral 7B model for generation...")
                    # Use Mistral model
                    response = mistral_model(
                        prompt,
                        max_tokens=200,  # Reasonable for plain text
                        temperature=0.7,
                        top_p=0.9,
                        top_k=40,
                        repeat_penalty=1.1,
                        stop=["User:", "Puddles:", "\n\n", "[/INST]"]
                    )
                    
                    generated_text = response['choices'][0]['text'].strip()
                    logger.info(f"Raw Mistral response: '{generated_text}'")
                    
                    # Clean up the response
                    if generated_text:
                        # Remove any remaining prompt artifacts
                        lines = generated_text.split('\n')
                        clean_lines = []
                        for line in lines:
                            line = line.strip()
                            if line and not line.startswith(('User:', 'Puddles:', 'System:', '[INST]', '[/INST]')):
                                clean_lines.append(line)
                        
                        if clean_lines:
                            cleaned_response = ' '.join(clean_lines)
                            logger.info(f"Cleaned Mistral response: '{cleaned_response}'")
                            return cleaned_response
                    
                    # If we get here, use fallback
                    logger.info("Mistral response empty/invalid - using fallback")
                    return generate_fallback_response(cleaned_content, user_name)
                    
                except Exception as e:
                    logger.error(f"Error generating Mistral response: {e}")
                    logger.info("Mistral generation failed - using fallback")
                    return generate_fallback_response(cleaned_content, user_name)
        
        # Run in executor to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, generate_in_thread)
        
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
        return f"Sup {user_name} 😏 What do you want? 🙄 Quack 🦆"
    
    # Thanks responses
    if any(word in message_lower for word in ['thank', 'thanks', 'appreciate', 'thx']):
        return f"Yeah yeah, you're welcome {user_name} 😒✨ Quack 🦆"
    
    # Knowledge-based responses for specific topics
    knowledge_responses = {

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
            return f"How to? {user_name}, just figure it out 🤷‍♂️💀 Or Google it idk Quack 🦆"
        
        if any(word in message_lower for word in ['what is', 'what are', 'what does']):
            # Try to extract what they're asking about
            words = message_lower.split()
            try:
                is_index = next(i for i, word in enumerate(words) if word in ['is', 'are', 'does'])
                if is_index < len(words) - 1:
                    topic = ' '.join(words[is_index + 1:]).replace('?', '').strip()
                    return f"'{topic}'? {user_name}, sounds made up to me 🙄📚 But sure whatever Quack 🦆"
            except:
                pass
        
        if any(word in message_lower for word in ['why', 'why is', 'why do', 'why does']):
            return f"Why? Because life is pain {user_name} 😩💀 That's why Quack 🦆"
        
        if any(word in message_lower for word in ['can you', 'could you', 'would you']):
            return f"Can I? Maybe {user_name}... but do I want to? 🤔😏 What's in it for me? Quack 🦆"
        
        # General question response
        if any(word in message_lower for word in question_words):
            return f"Questions questions {user_name} 🙄❓ Can't you just Google things? Quack 🦆"
    
    # Statement responses - try to engage with what they said
    if any(word in message_lower for word in ['i am', "i'm", 'i have', "i've", 'i need', 'i want', 'i like']):
        if any(word in message_lower for word in ['working on', 'building', 'creating', 'making']):
            return f"Working on something? {user_name}, let me guess... it's broken? 🔨💀 Quack 🦆"
        
        if any(word in message_lower for word in ['stuck', 'confused', 'problem', 'issue', 'error']):
            return f"Stuck again {user_name}? Skill issue tbh 😂🤷‍♂️ Quack 🦆"
        
        if any(word in message_lower for word in ['learning', 'studying', 'trying to understand']):
            return f"Learning? Good luck with that {user_name} 📚😴 Most people give up anyway Quack 🦆"
    
    # Look for specific requests
    if any(word in message_lower for word in ['show me', 'give me', 'tell me about', 'explain']):
        return f"Show you? {user_name}, I'm not your personal Google 🙄🔍 Figure it out Quack 🦆"
    
    # Conversational engagement based on content
    if len(message.split()) > 5:  # Longer messages deserve more thoughtful responses
        return f"Wow {user_name}, that's a lot of words 📝😴 TL;DR please? Quack 🦆"
    
    # Very short messages
    if len(message.split()) <= 2:
        return f"That's it? {user_name}, use your words 🗣️💀 Quack 🦆"
    
    # Default engaging responses (last resort)
    engaging_responses = [
        f"Cool story {user_name} 📚😑 Got anything actually interesting? Quack 🦆",
        f"Uh huh sure {user_name}... anyway 🙄✨ Quack 🦆",
        f"That's nice dear {user_name} 😏💤 What else you got? Quack 🦆",
        f"Fascinating stuff {user_name} 🥱 Truly riveting Quack 🦆"
    ]
    
    import random
    response = random.choice(engaging_responses)
    logger.info(f"Using default engaging response: {response[:50]}...")
    return response

async def handle_bot_mention(message: discord.Message, bot: commands.Bot) -> bool:
    """Handle when the bot is mentioned in a message"""
    
    # Check if AI chat is disabled for this server
    if await disable.is_feature_disabled(message.guild.id, "ai_chat"):
        return False
        
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
                    timeout=60.0  # 60 second timeout
                )
            except asyncio.TimeoutError:
                logger.error("⏰ Response generation timed out after 60 seconds")
                response = f"Sorry {message.author.display_name}, my response took too long to generate. Could you try asking again or rephrase your question? Quack 🦆"
            
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
    if model_loaded and mistral_model is not None:
        return "✅ Ready (Mistral 7B Model)"
    elif model_loaded:
        return "✅ Ready (Fallback System)"
    elif model_loading:
        return "⏳ Loading..."
    else:
        return "❌ Failed to load"

def download_mistral_model():
    """Download Mistral 7B model if none exists"""
    models_dir = Path("models")
    models_dir.mkdir(exist_ok=True)
    
    # Check for existing Mistral 7B model
    existing_models = list(models_dir.glob("*mistral*7b*.gguf"))
    if existing_models:
        logger.info(f"Found existing Mistral 7B model: {existing_models[0].name}")
        return str(existing_models[0])
    
    # Define Mistral 7B model
    model_info = {
        "name": "mistral-7b-instruct-v0.2.Q4_K_M.gguf",
        "url": "https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF/resolve/main/mistral-7b-instruct-v0.2.Q4_K_M.gguf",
        "size_mb": 4096,
        "description": "Mistral 7B Instruct v0.2 - High quality conversational model (4.1GB)"
    }
    
    model_path = models_dir / model_info["name"]
    
    logger.info(f"🤖 No Mistral 7B model found. Auto-downloading {model_info['description']}...")
    print(f"🤖 No Mistral 7B model found!")
    print(f"📦 Auto-downloading: {model_info['description']}")
    print(f"🔗 From: {model_info['url']}")
    print(f"💾 This will use ~{model_info['size_mb']}MB of disk space")
    print(f"⏳ This may take several minutes depending on your internet speed...")
    print()
    
    try:
        # Download with progress
        download_progress_hook.last_percent = 0
        import urllib.request
        urllib.request.urlretrieve(
            model_info["url"],
            str(model_path),
            reporthook=download_progress_hook
        )
        
        # Verify download
        if model_path.exists() and model_path.stat().st_size > 3_000_000_000:  # At least 3GB
            print(f"✅ Mistral 7B model downloaded successfully: {model_path.name}")
            print(f"📁 Saved to: {model_path}")
            logger.info(f"Successfully downloaded Mistral 7B model: {model_path}")
            return str(model_path)
        else:
            logger.error("Downloaded Mistral 7B model file seems corrupted or too small")
            if model_path.exists():
                model_path.unlink()  # Delete corrupted file
            return None
            
    except Exception as e:
        logger.error(f"Failed to download Mistral 7B model: {e}")
        print(f"❌ Failed to download Mistral 7B model: {e}")
        print("💡 You can manually download a Mistral 7B model to the 'models/' directory")
        print("   Recommended: https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF")
        if model_path.exists():
            model_path.unlink()  # Clean up partial download
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
                print(f"📥 Downloading Mistral 7B model... {percent}% ({mb_downloaded}MB / {mb_total}MB)")
                download_progress_hook.last_percent = percent
        elif not hasattr(download_progress_hook, 'last_percent'):
            download_progress_hook.last_percent = 0
            print(f"📥 Starting Mistral 7B model download... ({mb_total}MB total)")

# Alias for backward compatibility
setup_gpt4all_system = setup_ai_chat_system 