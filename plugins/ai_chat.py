"""
AI Chat Plugin for Discord Bot
Handles AI responses in designated channels using OpenAI API with dynamic server mapping
"""

import os
import json
import asyncio
import urllib.request
import urllib.error
import discord
from discord.ext import commands
import re
from urllib.parse import quote_plus
import html
from bot.global_config import load_global_settings

# AI Configuration
AI_ALLOWED_CHANNEL_ID = 1421161902343454932
ENABLE_AI_AUTOREPLY = True
AI_REPLY_COOLDOWN = 1
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
# SECURITY: key comes from env var ONLY. Set OPENAI_API_KEY in plugins/.env — never hardcode it here.

# Cooldown tracking
_last_ai_reply = {}

# Memory settings
MEMORY_DIR = "memories"
MEMORY_MAX_MESSAGES = 20

def load_ai_settings():
    """Load non-secret AI settings saved by the dashboard."""
    global AI_ALLOWED_CHANNEL_ID, ENABLE_AI_AUTOREPLY, AI_REPLY_COOLDOWN, MEMORY_MAX_MESSAGES
    settings_file = os.path.join(os.path.dirname(__file__), "ai_chat.py.settings.json")
    try:
        if not os.path.exists(settings_file):
            return
        with open(settings_file, "r", encoding="utf-8") as f:
            settings = json.load(f) or {}
        if settings.get("AI_ALLOWED_CHANNEL_ID") not in (None, ""):
            AI_ALLOWED_CHANNEL_ID = int(settings["AI_ALLOWED_CHANNEL_ID"])
        ENABLE_AI_AUTOREPLY = bool(settings.get("ENABLE_AI_AUTOREPLY", ENABLE_AI_AUTOREPLY))
        AI_REPLY_COOLDOWN = max(0, float(settings.get("AI_REPLY_COOLDOWN", AI_REPLY_COOLDOWN)))
        MEMORY_MAX_MESSAGES = max(1, int(settings.get("MEMORY_MAX_MESSAGES", MEMORY_MAX_MESSAGES)))
        print(f"AI: Settings loaded for channel {AI_ALLOWED_CHANNEL_ID}")
    except Exception as e:
        print(f"AI: Failed to load settings: {e}")


load_ai_settings()

# Server mapping cache
_server_structure = None
_channel_keywords = {}

# Role-based visibility filter
PUBLIC_ROLE_ID = 1168915030704672909  # Role that should see channels
DEV_ROLE_ID = 1347589804895768576  # Dev role ID (adjust if needed)

# Banned channels storage
BANNED_CHANNELS_FILE = "plugins/banned_channels.json"
_banned_channels = set()

# Keywords for channel mapping (English)
CHANNEL_KEYWORD_MAP = {
    # General communication
    "chat": ["general", "chat", "talk", "conversation"],
    "ai": ["ai", "bot", "assistant", "chatgpt", "gpt"],
    "announcements": ["announce", "news", "updates", "info"],
    
    # Support & Management  
    "support": ["support", "help", "ticket", "hr", "assistance", "human", "resources"],
    "management": ["manage", "admin", "staff", "mod", "leader"],
    "events": ["event", "convoy", "invite", "schedule", "meeting"],
    
    # VTC Related
    "convoy": ["convoy", "drive", "trucking", "tmp", "truckersmp"],
    "recruitment": ["recruit", "join", "apply", "application"],
    "rules": ["rule", "guideline", "regulation", "policy"],
    
    # Server improvement
    "suggestions": ["suggest", "suggestion", "idea", "improve", "better", "feedback"],
    
    # Categories
    "category": ["category", "section", "area", "zone"]
}

def ensure_memory_dir():
    try:
        os.makedirs(MEMORY_DIR, exist_ok=True)
    except Exception as e:
        print(f"Failed to ensure memory dir: {e}")


def _get_global_guild_id():
    gid = os.environ.get('GUILD_ID')
    if gid and str(gid).strip().isdigit():
        return int(gid)
    try:
        g = load_global_settings()
        if g and 'GUILD_ID' in g and str(g['GUILD_ID']).strip().isdigit():
            return int(g['GUILD_ID'])
    except Exception:
        pass
    return None

def load_banned_channels():
    """Load banned channels from file"""
    global _banned_channels
    try:
        if os.path.exists(BANNED_CHANNELS_FILE):
            with open(BANNED_CHANNELS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                _banned_channels = set(data.get("banned_channels", []))
                print(f"AI: Loaded {len(_banned_channels)} banned channels")
    except Exception as e:
        print(f"Failed to load banned channels: {e}")
        _banned_channels = set()

def save_banned_channels():
    """Save banned channels to file"""
    try:
        os.makedirs(os.path.dirname(BANNED_CHANNELS_FILE), exist_ok=True)
        with open(BANNED_CHANNELS_FILE, "w", encoding="utf-8") as f:
            json.dump({"banned_channels": list(_banned_channels)}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Failed to save banned channels: {e}")

def is_channel_banned(channel_id):
    """Check if channel is banned"""
    return channel_id in _banned_channels

def has_dev_permissions(user):
    """Check if user has dev role or higher"""
    if not hasattr(user, 'roles'):
        return False
    
    # Check for dev role or admin roles
    role_ids = [role.id for role in user.roles]
    return (DEV_ROLE_ID in role_ids or 
            any(role.name.lower() in ['admin', 'owner', 'developer'] for role in user.roles))

async def search_web(query, max_results=3):
    """Search the web using simple methods and return results"""
    try:
        search_results = []
        
        # For trucking-related queries, provide direct links
        query_lower = query.lower()
        
        if any(word in query_lower for word in ['truckersmp', 'tmp']):
            search_results.append({
                'title': 'TruckersMP - Official Website',
                'snippet': 'Official TruckersMP website with news, events, convoy information, and community features.',
                'url': 'https://truckersmp.com'
            })
            search_results.append({
                'title': 'TruckersMP Events',
                'snippet': 'Browse and participate in official TruckersMP events and convoys.',
                'url': 'https://truckersmp.com/events'
            })
        
        if any(word in query_lower for word in ['convoy', 'event']):
            search_results.append({
                'title': 'TruckersMP Events Calendar',
                'snippet': 'Check upcoming convoys and events in the TruckersMP community.',
                'url': 'https://truckersmp.com/events'
            })
        
        if any(word in query_lower for word in ['news', 'update', 'latest']):
            search_results.append({
                'title': 'TruckersMP News',
                'snippet': 'Latest news and updates from the TruckersMP team.',
                'url': 'https://truckersmp.com/news'
            })
        
        if any(word in query_lower for word in ['forum', 'discussion']):
            search_results.append({
                'title': 'TruckersMP Community Forum',
                'snippet': 'Join discussions, get help, and connect with other truckers.',
                'url': 'https://forum.truckersmp.com'
            })
        
        # Add DuckDuckGo search as fallback
        if not search_results:
            try:
                search_url = f"https://api.duckduckgo.com/?q={quote_plus(query)}&format=json&no_html=1&skip_disambig=1"
                
                def fetch_search():
                    req = urllib.request.Request(search_url)
                    req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
                    with urllib.request.urlopen(req, timeout=8) as response:
                        return json.loads(response.read().decode())
                
                result = await asyncio.to_thread(fetch_search)
                
                # Get instant answer if available
                if result.get('Abstract'):
                    search_results.append({
                        'title': result.get('Heading', 'Information'),
                        'snippet': result.get('Abstract', ''),
                        'url': result.get('AbstractURL', '')
                    })
                
            except Exception as e:
                print(f"DuckDuckGo search error: {e}")
        
        return search_results[:max_results]
        
    except Exception as e:
        print(f"Web search error: {e}")
        return []

async def get_truckersmp_info(query):
    """Get specific TruckersMP information"""
    try:
        # Check if it's a convoy/event query
        if any(word in query.lower() for word in ['convoy', 'event', 'tmp', 'truckersmp']):
            api_url = "https://api.truckersmp.com/v2/events"
            
            def fetch_events():
                req = urllib.request.Request(api_url)
                req.add_header('User-Agent', 'Nightwish-Trucking-Bot/1.0')
                with urllib.request.urlopen(req, timeout=10) as response:
                    return json.loads(response.read().decode())
            
            events_data = await asyncio.to_thread(fetch_events)
            
            if events_data.get('response') and isinstance(events_data['response'], list):
                events = events_data['response'][:3]  # Get first 3 events
                results = []
                
                for event in events:
                    if isinstance(event, dict):
                        event_info = {
                            'title': f"TMP Event: {event.get('name', 'Unknown')}",
                            'snippet': f"Start: {event.get('start_at', 'Unknown')} | Server: {event.get('server', {}).get('name', 'Unknown') if event.get('server') else 'Unknown'}",
                            'url': f"https://truckersmp.com/events/{event.get('id', '')}"
                        }
                        results.append(event_info)
                
                return results
            else:
                print(f"TruckersMP API response format unexpected: {events_data}")
                return []
        
        # Fallback to general TMP website
        return [{
            'title': 'TruckersMP - Official Website',
            'snippet': 'Official TruckersMP website with latest news, events, and community information.',
            'url': 'https://truckersmp.com'
        }]
        
    except Exception as e:
        print(f"TruckersMP API error: {e}")
        return []

def should_search_web(message):
    """Determine if message needs web search"""
    search_keywords = [
        'search', 'find', 'google', 'web', 'internet', 'lookup', 'check online',
        'truckersmp', 'tmp', 'convoy', 'event', 'news', 'update', 'latest',
        'what is', 'who is', 'how to', 'when is', 'where is'
    ]
    
    message_lower = message.lower()
    return any(keyword in message_lower for keyword in search_keywords)

def memory_path_for_channel(channel_id):
    ensure_memory_dir()
    return os.path.join(MEMORY_DIR, f"{channel_id}.json")

def load_memory(channel_id):
    path = memory_path_for_channel(channel_id)
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
    except Exception as e:
        print(f"Failed to load memory for {channel_id}: {e}")
    return []

def save_memory(channel_id, messages):
    path = memory_path_for_channel(channel_id)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Failed to save memory for {channel_id}: {e}")

def append_memory(channel_id, role, content):
    msgs = load_memory(channel_id)
    msgs.append({"role": role, "content": content})
    save_memory(channel_id, msgs)

def get_memory_messages_for_openai(channel_id):
    raw = load_memory(channel_id)
    out = []
    for item in raw:
        if isinstance(item, dict) and item.get("role") and item.get("content"):
            out.append({"role": item.get("role"), "content": item.get("content")})
    return out

def is_channel_visible_to_role(channel, role_id):
    """Check if channel is visible to specific role"""
    try:
        guild = channel.guild
        role = guild.get_role(role_id)
        if not role:
            return False
        
        # Check channel permissions for the role
        permissions = channel.permissions_for(role)
        return permissions.view_channel
    except Exception as e:
        print(f"Error checking channel visibility: {e}")
        return False

async def map_server_structure(bot, guild_id):
    """Dynamically map server structure with keywords, filtering by role visibility"""
    global _server_structure, _channel_keywords
    
    guild = discord.utils.get(bot.guilds, id=guild_id)
    if not guild:
        return "Server not found"
    
    public_role = guild.get_role(PUBLIC_ROLE_ID)
    if not public_role:
        print(f"AI: Warning - Public role {PUBLIC_ROLE_ID} not found")
    
    print(f"AI: Mapping server structure for {guild.name} (filtering for public visibility)")
    
    structure = {
        "guild_name": guild.name,
        "guild_id": guild.id,
        "categories": {},
        "channels": {},
        "roles": {}
    }
    
    # Clear previous keywords
    _channel_keywords = {}
    
    visible_count = 0
    total_count = 0
    
    # Map categories and channels
    for category in guild.categories:
        cat_info = {
            "name": category.name,
            "id": category.id,
            "channels": []
        }
        
        for channel in category.channels:
            if isinstance(channel, discord.TextChannel):
                total_count += 1
                
                # Skip channels ending with "wip"
                if channel.name.lower().endswith("wip"):
                    continue
                
                # Skip banned channels
                if is_channel_banned(channel.id):
                    continue
                
                # Only include channels visible to the public role
                if is_channel_visible_to_role(channel, PUBLIC_ROLE_ID):
                    visible_count += 1
                    channel_info = {
                        "name": channel.name,
                        "id": channel.id,
                        "topic": channel.topic or "",
                        "category": category.name,
                        "mention": f"<#{channel.id}>"
                    }
                    cat_info["channels"].append(channel_info)
                    structure["channels"][channel.id] = channel_info
                    
                    # Build keyword mapping
                    _add_channel_keywords(channel.name, channel.topic or "", channel.id)
        
        # Only add category if it has visible channels
        if cat_info["channels"]:
            structure["categories"][category.id] = cat_info
    
    # Map standalone channels (no category)
    for channel in guild.text_channels:
        if not channel.category:
            total_count += 1
            
            # Skip channels ending with "wip"
            if channel.name.lower().endswith("wip"):
                continue
            
            # Skip banned channels
            if is_channel_banned(channel.id):
                continue
            
            # Only include channels visible to the public role
            if is_channel_visible_to_role(channel, PUBLIC_ROLE_ID):
                visible_count += 1
                channel_info = {
                    "name": channel.name,
                    "id": channel.id,
                    "topic": channel.topic or "",
                    "category": "No Category",
                    "mention": f"<#{channel.id}>"
                }
                structure["channels"][channel.id] = channel_info
                _add_channel_keywords(channel.name, channel.topic or "", channel.id)
    
    # Map important roles
    important_role_names = ['admin', 'mod', 'staff', 'management', 'leader', 'owner']
    for role in guild.roles:
        if any(keyword in role.name.lower() for keyword in important_role_names):
            structure["roles"][role.id] = {
                "name": role.name,
                "id": role.id,
                "mention": f"<@&{role.id}>"
            }
    
    _server_structure = structure
    print(f"AI: Mapped {visible_count}/{total_count} visible channels in {len(structure['categories'])} categories")
    return structure

def _add_channel_keywords(channel_name, topic, channel_id):
    """Add channel to keyword mapping"""
    global _channel_keywords
    
    # Normalize text for keyword matching
    searchable_text = f"{channel_name} {topic}".lower()
    
    for category, keywords in CHANNEL_KEYWORD_MAP.items():
        for keyword in keywords:
            if keyword in searchable_text:
                if category not in _channel_keywords:
                    _channel_keywords[category] = []
                if channel_id not in _channel_keywords[category]:
                    _channel_keywords[category].append(channel_id)

def find_channels_by_keywords(keywords):
    """Find channels matching keywords (only visible channels)"""
    if not _server_structure:
        return []
    
    found_channels = []
    keywords_lower = [k.lower() for k in keywords if k]
    
    for keyword in keywords_lower:
        # Direct keyword match
        if keyword in _channel_keywords:
            for channel_id in _channel_keywords[keyword]:
                # Only include channels that are in our visible structure
                if channel_id in _server_structure["channels"]:
                    channel_info = _server_structure["channels"][channel_id]
                    if channel_info not in found_channels:
                        found_channels.append(channel_info)
        
        # Fuzzy match in channel names and topics (only visible channels)
        for channel_id, channel_info in _server_structure["channels"].items():
            searchable = f"{channel_info['name']} {channel_info['topic']}".lower()
            if keyword in searchable and channel_info not in found_channels:
                found_channels.append(channel_info)
    
    return found_channels

def create_server_context():
    """Create context about server structure for AI (public channels only)"""
    if not _server_structure:
        return "Server structure not mapped yet."
    
    context = f"**{_server_structure['guild_name']} Public Channels:**\n\n"
    
    # Add categories and channels
    for cat_id, cat_info in _server_structure["categories"].items():
        context += f"📁 **{cat_info['name']}**\n"
        for channel in cat_info["channels"]:
            topic_text = f" - {channel['topic'][:50]}..." if channel['topic'] else ""
            context += f"  • {channel['mention']} #{channel['name']}{topic_text}\n"
        context += "\n"
    
    # Add standalone channels
    standalone = [ch for ch in _server_structure["channels"].values() if ch["category"] == "No Category"]
    if standalone:
        context += "📄 **Other Channels:**\n"
        for channel in standalone:
            topic_text = f" - {channel['topic'][:50]}..." if channel['topic'] else ""
            context += f"  • {channel['mention']} #{channel['name']}{topic_text}\n"
    
    return context

def enhance_message_with_channel_links(message):
    """Fix channel references and add suggestions (excludes banned channels)"""
    if not _server_structure:
        return message
    
    enhanced_message = message
    
    # Replace #channel-name patterns with proper <#id> mentions
    for channel_id, channel_info in _server_structure["channels"].items():
        if is_channel_banned(channel_id):
            continue
            
        channel_name = channel_info["name"]
        # Look for patterns like #channel-name or #channel_name and replace with <#id>
        patterns = [
            f"#{channel_name}",
            f"#{channel_name.replace('-', '_')}",
            f"#{channel_name.replace('_', '-')}",
            f"#❔︱{channel_name}",
            f"#🎟︱{channel_name}",
            f"#💬︱{channel_name}"
        ]
        
        for pattern in patterns:
            if pattern in enhanced_message:
                enhanced_message = enhanced_message.replace(pattern, channel_info["mention"])
    
    # Look for words that might reference channels for suggestions
    words = re.findall(r'\b\w+\b', message.lower())
    channel_suggestions = find_channels_by_keywords(words)
    
    # Filter out banned channels from suggestions
    filtered_suggestions = [ch for ch in channel_suggestions if not is_channel_banned(ch['id'])]
    
    # Only add suggestions if no proper mentions were already in the message
    if filtered_suggestions and "<#" not in enhanced_message and len(filtered_suggestions) <= 3:
        enhanced_message += "\n\n**Relevant channels:**\n"
        for channel in filtered_suggestions[:2]:  # Limit to top 2
            enhanced_message += f"• {channel['mention']}\n"
    
    return enhanced_message

def call_openai_api(api_key, system_prompt, user_prompt, memory_messages=None, max_tokens=400):
    if memory_messages:
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(memory_messages[-MEMORY_MAX_MESSAGES:])
        messages.append({"role": "user", "content": user_prompt})
    else:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

    payload = {
        "model": "gpt-3.5-turbo",
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.7
    }
    
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(OPENAI_API_URL, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {api_key}")
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            if result.get("choices") and len(result["choices"]) > 0:
                return result["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode()
            print(f"OpenAI HTTPError: {e.code} {err_body}")
        except Exception:
            print(f"OpenAI HTTPError: {e}")
    except Exception as e:
        print(f"OpenAI request failed: {e}")
    return None

async def generate_ai_reply(system_prompt, user_prompt, channel_id=None, max_tokens=400):
    """Async wrapper around synchronous OpenAI call with server context"""
    try:
        if not ENABLE_AI_AUTOREPLY:
            print("AI autoreply is currently disabled")
            return None

        api_key = os.environ.get(OPENAI_API_KEY_ENV)
        if not api_key:
            print("No OpenAI API key found")
            return None

        # Add server structure context to system prompt
        server_context = create_server_context()
        enhanced_system_prompt = f"{system_prompt}\n\n{server_context}\n\nWhen users ask about channels, locations, or where to do something, refer them to the appropriate channels using their @mentions."
        
        # Get conversation memory if channel_id provided
        memory_messages = get_memory_messages_for_openai(channel_id) if channel_id else None
        
        result = await asyncio.to_thread(call_openai_api, api_key, enhanced_system_prompt, user_prompt, memory_messages, max_tokens)

        if not result:
            print("AI call returned no content or failed")
            return None

        # Enhance response with channel links
        enhanced_result = enhance_message_with_channel_links(result)

        snippet = enhanced_result if len(enhanced_result) <= 800 else enhanced_result[:800] + "..."
        print(f"AI suggestion generated (len={len(enhanced_result)}): {snippet}")
        return enhanced_result
    except Exception as e:
        print(f"generate_ai_reply error: {e}")
        return None

class AIChatCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        print("AI Chat plugin initialized")

    async def cog_load(self):
        """Called when the cog is loaded - map server structure"""
        # Load banned channels first
        load_banned_channels()
        
        guild_id = _get_global_guild_id() or 1168883480583745587
        await map_server_structure(self.bot, guild_id)

    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignore bot's own messages
        if message.author == self.bot.user:
            return

        # Only process messages in the AI allowed channel
        if getattr(message.channel, 'id', None) != AI_ALLOWED_CHANNEL_ID:
            return

        # Skip empty messages or bot commands
        content = (message.content or "").strip()
        if not content or content.startswith('!'):
            return

        # Cooldown check
        current_time = asyncio.get_event_loop().time()
        last_reply = _last_ai_reply.get(message.channel.id, 0)
        if current_time - last_reply < AI_REPLY_COOLDOWN:
            return

        # Generate AI response with server context
        system_prompt = """You are Nightwish Trucking's Discord AI assistant with internet access.

Key Information:
- VTC Name: Nightwish Trucking (ID: 67445)
- Focus: ETS2/ATS convoys and events
- Server Language: Mix of Czech and English (respond in English)
- Convoy Requirements: Must start at 18:00 UTC or later

You help with:
- Server navigation and channel information
- VTC information and convoy scheduling
- General trucking questions and web searches
- TruckersMP events and news (with live data)
- Directing users to appropriate channels

Web Search Capabilities:
- You can access current TruckersMP events and information
- You can search the web for trucking-related information
- When provided with web search results, use them to give accurate, up-to-date information

IMPORTANT: When referring to Discord channels, ALWAYS use the clickable format <#channel_id> (like <#1320020298531209256>). NEVER use # followed by channel name (like #channel-name) as those are not clickable. Only use the channel mentions that are provided in your server context."""

        try:
            # Add user message to memory
            append_memory(message.channel.id, "user", content)
            
            # Check if we should search the web
            web_results = []
            if should_search_web(content):
                print(f"AI: Performing web search for: {content}")
                
                # Try TruckersMP specific search first
                if any(word in content.lower() for word in ['truckersmp', 'tmp', 'convoy', 'event']):
                    web_results = await get_truckersmp_info(content)
                
                # Fallback to general web search
                if not web_results:
                    web_results = await search_web(content)
                
                if web_results:
                    print(f"AI: Found {len(web_results)} web results")
            
            # Generate AI response with web context
            enhanced_prompt = system_prompt
            if web_results:
                web_context = "\n\nRecent web search results:\n"
                for i, result in enumerate(web_results, 1):
                    web_context += f"{i}. {result['title']}\n   {result['snippet']}\n   URL: {result['url']}\n\n"
                enhanced_prompt += web_context + "Use this information to provide a more accurate and up-to-date response."
            
            ai_response = await generate_ai_reply(enhanced_prompt, content, message.channel.id, 600)
            
            if ai_response:
                # Send response
                await message.channel.send(ai_response)
                
                # Add AI response to memory
                append_memory(message.channel.id, "assistant", ai_response)
                
                # Update cooldown
                _last_ai_reply[message.channel.id] = current_time
                print(f"AI replied in channel {message.channel.id}")
            else:
                print("AI response generation failed")
                
        except Exception as e:
            print(f"AI message handler error: {e}")

async def setup(bot):
    # Add AI Chat Cog
    await bot.add_cog(AIChatCog(bot))
    print("AI: cog registered")
    
    # Create AI command group
    class AIGroup(discord.app_commands.Group):
        def __init__(self):
            super().__init__(name="ai", description="AI channel management commands")

        @discord.app_commands.command(name="ban", description="Ban a channel from AI responses (Dev+ only)")
        @discord.app_commands.describe(channel="Channel to ban from AI responses")
        async def ban_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
            """Ban a channel from appearing in AI responses"""
            if not has_dev_permissions(interaction.user):
                await interaction.response.send_message("❌ You need Developer role or higher to use this command.", ephemeral=True)
                return
            
            global _banned_channels
            _banned_channels.add(channel.id)
            save_banned_channels()
            
            await interaction.response.send_message(f"✅ Channel {channel.mention} has been banned from AI responses.", ephemeral=True)
            
            # Remap server structure to reflect changes
            guild_id = _get_global_guild_id() or 1168883480583745587
            await map_server_structure(bot, guild_id)
            
            # Clear AI conversation memory to remove old channel references
            ai_channel_memory_path = memory_path_for_channel(1421161902343454932)
            if os.path.exists(ai_channel_memory_path):
                os.remove(ai_channel_memory_path)
                print(f"AI: Cleared conversation memory due to channel ban")
            
            print(f"AI: Channel {channel.name} ({channel.id}) banned by {interaction.user}")

        @discord.app_commands.command(name="unban", description="Unban a channel from AI responses (Dev+ only)")
        @discord.app_commands.describe(channel="Channel to unban from AI responses")
        async def unban_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
            """Unban a channel from appearing in AI responses"""
            if not has_dev_permissions(interaction.user):
                await interaction.response.send_message("❌ You need Developer role or higher to use this command.", ephemeral=True)
                return
            
            global _banned_channels
            if channel.id in _banned_channels:
                _banned_channels.remove(channel.id)
                save_banned_channels()
                await interaction.response.send_message(f"✅ Channel {channel.mention} has been unbanned from AI responses.", ephemeral=True)
                
                # Remap server structure to reflect changes
                guild_id = _get_global_guild_id() or 1168883480583745587
                await map_server_structure(bot, guild_id)
                
                # Clear AI conversation memory to refresh channel references
                ai_channel_memory_path = memory_path_for_channel(1421161902343454932)
                if os.path.exists(ai_channel_memory_path):
                    os.remove(ai_channel_memory_path)
                    print(f"AI: Cleared conversation memory due to channel unban")
                
                print(f"AI: Channel {channel.name} ({channel.id}) unbanned by {interaction.user}")
            else:
                await interaction.response.send_message(f"❌ Channel {channel.mention} is not currently banned.", ephemeral=True)

        @discord.app_commands.command(name="list", description="List all banned channels (Dev+ only)")
        async def list_banned_channels(self, interaction: discord.Interaction):
            """List all channels banned from AI responses"""
            if not has_dev_permissions(interaction.user):
                await interaction.response.send_message("❌ You need Developer role or higher to use this command.", ephemeral=True)
                return
            
            if not _banned_channels:
                await interaction.response.send_message("✅ No channels are currently banned from AI responses.", ephemeral=True)
                return
            
            guild = interaction.guild
            banned_list = []
            for channel_id in _banned_channels:
                channel = guild.get_channel(channel_id)
                if channel:
                    banned_list.append(f"• {channel.mention} (`{channel.id}`)")
                else:
                    banned_list.append(f"• Deleted channel (`{channel_id}`)")
            
            response = f"**Banned Channels ({len(_banned_channels)}):**\n" + "\n".join(banned_list)
            await interaction.response.send_message(response[:2000], ephemeral=True)

    # Add the command group to the bot
    bot.tree.add_command(AIGroup())
    
    print("AI Chat plugin loaded successfully")