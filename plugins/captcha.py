"""
Captcha Plugin for Discord Bot
Requires new members to complete captcha verification before accessing the server
"""

import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import random
import string
import json
import os
from datetime import datetime, timedelta

# Configuration
GUILD_ID = 1168883480583745587
CAPTCHA_CHANNEL_ID = 1319988147572183040  # Channel for captcha verification
VERIFIED_ROLE_ID = 1168915030704672909    # Role to give after verification
UNVERIFIED_ROLE_ID = None  # Optional: role for unverified users
ADMIN_ROLE_ID = 1169176570150260776
DEV_ROLE_ID = 1347589804895768576

# Prefer global GUILD_ID from environment if provided by dashboard
try:
    env_gid = os.environ.get('GUILD_ID')
    if env_gid and str(env_gid).strip().isdigit():
        GUILD_ID = int(env_gid)
        print(f"Captcha: using global GUILD_ID from environment: {GUILD_ID}")
except Exception:
    pass

# Captcha storage
CAPTCHA_FILE = os.path.join(os.path.dirname(__file__), "captcha_data.json")
_captcha_sessions = {}  # user_id: {'challenge': dict, 'expires': datetime, 'attempts': int}

# Dashboard-editable captcha settings
CAPTCHA_ENABLED = True

# Advanced captcha settings
CAPTCHA_SETTINGS = {
    'enabled_types': ['text', 'math', 'pattern', 'question'],  # Which types to use
    'difficulty': 'medium',  # easy, medium, hard
    'image_chance': 0.5,  # Chance of background image (0.0 to 1.0)
    'timeout_minutes': 10,  # How long users have to complete
    'max_attempts': 3,  # Max attempts before new challenge required
}

def load_captcha_settings():
    """Load dashboard settings without making the settings file mandatory."""
    global GUILD_ID, CAPTCHA_CHANNEL_ID, VERIFIED_ROLE_ID, UNVERIFIED_ROLE_ID
    global ADMIN_ROLE_ID, DEV_ROLE_ID, CAPTCHA_ENABLED
    settings_file = os.path.join(os.path.dirname(__file__), "captcha.py.settings.json")
    try:
        if not os.path.exists(settings_file):
            return
        with open(settings_file, "r", encoding="utf-8") as f:
            settings = json.load(f) or {}
        for name in ("CAPTCHA_CHANNEL_ID", "VERIFIED_ROLE_ID", "UNVERIFIED_ROLE_ID", "ADMIN_ROLE_ID", "DEV_ROLE_ID"):
            if settings.get(name) not in (None, ""):
                globals()[name] = int(settings[name])
        CAPTCHA_ENABLED = bool(settings.get("CAPTCHA_ENABLED", CAPTCHA_ENABLED))
        for name in ("difficulty", "timeout_minutes", "max_attempts", "image_chance", "enabled_types"):
            if name in settings:
                CAPTCHA_SETTINGS[name] = settings[name]
        CAPTCHA_SETTINGS['timeout_minutes'] = max(1, int(CAPTCHA_SETTINGS['timeout_minutes']))
        CAPTCHA_SETTINGS['max_attempts'] = max(1, int(CAPTCHA_SETTINGS['max_attempts']))
        CAPTCHA_SETTINGS['image_chance'] = min(1.0, max(0.0, float(CAPTCHA_SETTINGS['image_chance'])))
        allowed = {'text', 'math', 'pattern', 'question'}
        CAPTCHA_SETTINGS['enabled_types'] = [item for item in CAPTCHA_SETTINGS['enabled_types'] if item in allowed] or ['text']
    except Exception as e:
        print(f"Captcha: failed to load settings: {e}")


load_captcha_settings()

def load_captcha_data():
    """Load captcha data from file"""
    global _captcha_sessions
    try:
        if os.path.exists(CAPTCHA_FILE):
            with open(CAPTCHA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Convert string timestamps back to datetime objects
                for user_id, session in data.items():
                    if 'expires' in session:
                        session['expires'] = datetime.fromisoformat(session['expires'])
                _captcha_sessions = data
                print(f"Captcha: Loaded {len(_captcha_sessions)} sessions")
    except Exception as e:
        print(f"Failed to load captcha data: {e}")
        _captcha_sessions = {}

def save_captcha_data():
    """Save captcha data to file"""
    try:
        os.makedirs(os.path.dirname(CAPTCHA_FILE), exist_ok=True)
        # Convert datetime objects to strings for JSON serialization
        data = {}
        for user_id, session in _captcha_sessions.items():
            session_copy = session.copy()
            if 'expires' in session_copy:
                session_copy['expires'] = session_copy['expires'].isoformat()
            data[user_id] = session_copy
        
        with open(CAPTCHA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Captcha: Saved {len(_captcha_sessions)} sessions")
    except Exception as e:
        print(f"Failed to save captcha data: {e}")

def generate_captcha_challenge():
    """Generate different types of captcha challenges"""
    captcha_type = random.choice(CAPTCHA_SETTINGS['enabled_types'])
    difficulty = CAPTCHA_SETTINGS['difficulty']
    
    if captcha_type == 'text':
        # Mix of letters and numbers, avoiding confusing characters
        if difficulty == 'easy':
            chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
            length = random.choice([4, 5])
        elif difficulty == 'medium':
            chars = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789"
            length = random.choice([5, 6])
        else:  # hard
            chars = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789!@#$%"
            length = random.choice([6, 7, 8])
        
        code = ''.join(random.choices(chars, k=length))
        return {
            'type': 'text',
            'challenge': f"Type this code: **{code}**",
            'answer': code,
            'description': 'Enter the code exactly as shown (case-sensitive)'
        }
    
    elif captcha_type == 'math':
        # Math problems based on difficulty
        if difficulty == 'easy':
            operations = [
                lambda: (random.randint(1, 20), random.randint(1, 10), '+'),
                lambda: (random.randint(10, 30), random.randint(1, 9), '-'),
            ]
        elif difficulty == 'medium':
            operations = [
                lambda: (random.randint(10, 50), random.randint(1, 20), '+'),
                lambda: (random.randint(20, 100), random.randint(1, 19), '-'),
                lambda: (random.randint(2, 12), random.randint(2, 9), '*'),
            ]
        else:  # hard
            operations = [
                lambda: (random.randint(25, 100), random.randint(10, 50), '+'),
                lambda: (random.randint(50, 200), random.randint(10, 49), '-'),
                lambda: (random.randint(5, 15), random.randint(3, 12), '*'),
                lambda: (random.randint(20, 100), random.choice([2, 4, 5, 10]), '/'),
            ]
        
        op_func = random.choice(operations)
        a, b, operator = op_func()
        
        if operator == '+':
            answer = a + b
        elif operator == '-':
            answer = a - b
        elif operator == '*':
            answer = a * b
        elif operator == '/':
            answer = a // b  # Integer division for cleaner answers
        
        return {
            'type': 'math',
            'challenge': f"Solve: **{a} {operator} {b} = ?**",
            'answer': str(answer),
            'description': 'Enter the numerical answer'
        }
    
    elif captcha_type == 'pattern':
        # Pattern recognition
        patterns = [
            {'seq': [2, 4, 6, 8, '?'], 'answer': '10', 'desc': 'even numbers'},
            {'seq': [1, 3, 5, 7, '?'], 'answer': '9', 'desc': 'odd numbers'},
            {'seq': [5, 10, 15, 20, '?'], 'answer': '25', 'desc': 'multiples of 5'},
            {'seq': [1, 4, 9, 16, '?'], 'answer': '25', 'desc': 'square numbers'},
            {'seq': ['A', 'C', 'E', 'G', '?'], 'answer': 'I', 'desc': 'every other letter'},
        ]
        
        pattern = random.choice(patterns)
        return {
            'type': 'pattern',
            'challenge': f"Complete the sequence: **{' → '.join(map(str, pattern['seq']))}**",
            'answer': pattern['answer'],
            'description': 'Enter the next item in the sequence'
        }
    
    elif captcha_type == 'question':
        # Knowledge questions based on difficulty
        if difficulty == 'easy':
            questions = [
                {'q': 'What color do you get when you mix red and blue?', 'a': 'purple'},
                {'q': 'How many days are in a week?', 'a': '7'},
                {'q': 'What is the opposite of hot?', 'a': 'cold'},
                {'q': 'What comes after Monday?', 'a': 'tuesday'},
                {'q': 'What is the first letter of the alphabet?', 'a': 'a'},
                {'q': 'How many months are in a year?', 'a': '12'},
            ]
        elif difficulty == 'medium':
            questions = [
                {'q': 'How many wheels does a truck typically have? (number)', 'a': '18'},
                {'q': 'Type "truck" backwards:', 'a': 'kcurt'},
                {'q': 'What is the capital of France?', 'a': 'paris'},
                {'q': 'How many minutes are in an hour?', 'a': '60'},
                {'q': 'What planet do we live on?', 'a': 'earth'},
                {'q': 'What is 5 + 5?', 'a': '10'},
                {'q': 'What comes before Friday?', 'a': 'thursday'},
                {'q': 'How many sides does a triangle have?', 'a': '3'},
                {'q': 'What is main language of bread(the developer for Nightwish)', 'a': 'czech'},
            ]
        else:  # hard
            questions = [
                {'q': 'What is the largest ocean on Earth?', 'a': 'pacific'},
                {'q': 'In what year did World War II end?', 'a': '1945'},
                {'q': 'What is the chemical symbol for gold?', 'a': 'au'},
                {'q': 'How many continents are there?', 'a': '7'},
                {'q': 'What is the square root of 64?', 'a': '8'},
                {'q': 'Complete: "To be or not to _____"', 'a': 'be'},
                {'q': 'What gas do plants absorb from the atmosphere?', 'a': 'carbon dioxide'},
                {'q': 'What is the longest river in the world?', 'a': 'nile'},
            ]
        
        question = random.choice(questions)
        return {
            'type': 'question',
            'challenge': f"**{question['q']}**",
            'answer': question['a'].lower(),
            'description': 'Answer in English (case-insensitive)'
        }

def generate_captcha_image_url():
    """Generate random captcha background images"""
    backgrounds = [
        "https://images.unsplash.com/photo-1558618047-3c8c76ca7d13?w=400&h=200&fit=crop",  # Truck
        "https://images.unsplash.com/photo-1601584115197-04ecc0da31d7?w=400&h=200&fit=crop",  # Highway
        "https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=400&h=200&fit=crop",  # Road
        "https://images.unsplash.com/photo-1449824913935-59a10b8d2000?w=400&h=200&fit=crop",  # Landscape
        "https://images.unsplash.com/photo-1440342359743-84fcb8c21f21?w=400&h=200&fit=crop",  # Mountains
        "https://images.unsplash.com/photo-1542051841857-5f90071e7989?w=400&h=200&fit=crop",  # City
        "https://images.unsplash.com/photo-1511593358241-7eea1f3c84e5?w=400&h=200&fit=crop",  # Architecture
        "https://images.unsplash.com/photo-1470071459604-3b5ec3a7fe05?w=400&h=200&fit=crop",  # Stars
        "https://images.unsplash.com/photo-1501594907352-04cda38ebc29?w=400&h=200&fit=crop",  # Abstract
        "https://images.unsplash.com/photo-1518837695005-2083093ee35b?w=400&h=200&fit=crop",  # Ocean
        "https://images.unsplash.com/photo-1441974231531-c6227db76b6e?w=400&h=200&fit=crop",  # Forest
        "https://images.unsplash.com/photo-1509773896068-7fd415d91e2e?w=400&h=200&fit=crop",  # Desert
    ]
    return random.choice(backgrounds)

def has_admin_permissions(user):
    """Check if user has admin role or higher"""
    if not hasattr(user, 'roles'):
        return False
    
    role_ids = [role.id for role in user.roles]
    return (ADMIN_ROLE_ID in role_ids or 
            DEV_ROLE_ID in role_ids or
            any(role.name.lower() in ['admin', 'owner', 'developer'] for role in user.roles))

def create_captcha_embed(member, challenge):
    """Create captcha verification embed"""
    embed = discord.Embed(
        title="🔐 Server Verification Required",
        description=f"Welcome to **Nightwish Trucking**, {member.mention}!\n\n"
                   f"To access the server, please complete the verification below:",
        color=discord.Color.orange()
    )
    
    # Add challenge type indicator
    type_emojis = {
        'text': '🔤',
        'math': '🧮', 
        'pattern': '🔢',
        'question': '❓'
    }
    
    embed.add_field(
        name=f"{type_emojis.get(challenge['type'], '🎯')} {challenge['type'].title()} Challenge:",
        value=challenge['challenge'],
        inline=False
    )
    
    embed.add_field(
        name="📝 Instructions:",
        value=f"• {challenge['description']}\n"
              f"• You have {CAPTCHA_SETTINGS['timeout_minutes']} minutes to verify\n"
              f"• After {CAPTCHA_SETTINGS['max_attempts']} failed attempts, request a new challenge",
        inline=False
    )
    
    embed.add_field(
        name="❓ Having trouble?",
        value="Contact a staff member if you need help with verification.",
        inline=False
    )
    
    embed.set_thumbnail(url=member.display_avatar.url)
    
    # Add random background image based on settings
    if random.random() < CAPTCHA_SETTINGS['image_chance']:
        embed.set_image(url=generate_captcha_image_url())
    
    embed.set_footer(text="Nightwish Trucking • Security Verification")
    
    return embed

class VerificationRequestView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # Persistent view

    @discord.ui.button(label="🔐 Request Verification", style=discord.ButtonStyle.primary, custom_id="request_verification")
    async def request_verification(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        
        # Check if already verified
        guild = interaction.guild
        verified_role = guild.get_role(VERIFIED_ROLE_ID)
        if verified_role and verified_role in member.roles:
            await interaction.response.send_message("✅ You are already verified!", ephemeral=True)
            return
        
        # Generate captcha challenge
        challenge = generate_captcha_challenge()
        expires = datetime.now() + timedelta(minutes=CAPTCHA_SETTINGS['timeout_minutes'])
        
        _captcha_sessions[member.id] = {
            'challenge': challenge,
            'expires': expires,
            'attempts': 0
        }
        save_captcha_data()
        
        # Send captcha as ephemeral response
        embed = create_captcha_embed(member, challenge)
        view = CaptchaView(member)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        print(f"Captcha: Sent verification request to {member}")

class CaptchaView(discord.ui.View):
    def __init__(self, member):
        super().__init__(timeout=CAPTCHA_SETTINGS['timeout_minutes'] * 60)
        self.member = member

    @discord.ui.button(label="🔄 New Challenge", style=discord.ButtonStyle.secondary)
    async def new_code(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.member.id:
            await interaction.response.send_message("❌ This verification is not for you.", ephemeral=True)
            return
        
        # Generate new challenge
        challenge = generate_captcha_challenge()
        expires = datetime.now() + timedelta(minutes=CAPTCHA_SETTINGS['timeout_minutes'])
        
        _captcha_sessions[self.member.id] = {
            'challenge': challenge,
            'expires': expires,
            'attempts': 0
        }
        save_captcha_data()
        
        embed = create_captcha_embed(self.member, challenge)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="❓ Help", style=discord.ButtonStyle.secondary)
    async def help_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.member.id:
            await interaction.response.send_message("❌ This verification is not for you.", ephemeral=True)
            return
        
        help_embed = discord.Embed(
            title="❓ Captcha Help",
            description="Having trouble with verification?",
            color=discord.Color.blue()
        )
        
        help_embed.add_field(
            name="📝 How to verify:",
            value="1. Look at the code in the embed above\n"
                  "2. Type the code exactly in this channel\n"
                  "3. Press Enter to send\n"
                  "4. Wait for verification",
            inline=False
        )
        
        help_embed.add_field(
            name="⚠️ Common issues:",
            value="• Make sure the code is typed exactly\n"
                  "• Code is case-sensitive (capital letters)\n"
                  "• Don't include extra spaces\n"
                  "• Use 'New Challenge' if your challenge expired",
            inline=False
        )
        
        await interaction.response.send_message(embed=help_embed, ephemeral=True)

class CaptchaCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.captcha_enabled = CAPTCHA_ENABLED
        print("Captcha plugin initialized")

    async def send_verification_embed(self):
        """Send the persistent verification embed with button"""
        print(f"Captcha: Attempting to send verification embed...")
        
        guild = self.bot.get_guild(GUILD_ID)
        if not guild:
            print(f"Captcha: Guild {GUILD_ID} not found")
            return
        
        print(f"Captcha: Guild found: {guild.name}")
        
        captcha_channel = self.bot.get_channel(CAPTCHA_CHANNEL_ID) or guild.get_channel(CAPTCHA_CHANNEL_ID)
        if not captcha_channel:
            try:
                captcha_channel = await self.bot.fetch_channel(CAPTCHA_CHANNEL_ID)
            except Exception as e:
                print(f"Captcha: failed to fetch channel {CAPTCHA_CHANNEL_ID}: {e}")
        if not captcha_channel:
            print(f"Captcha: Channel {CAPTCHA_CHANNEL_ID} not found")
            print(f"Captcha: Available channels: {[ch.name + ' (' + str(ch.id) + ')' for ch in guild.text_channels]}")
            return
        
        print(f"Captcha: Channel found: {captcha_channel.name}")
        
        # Check bot permissions
        bot_member = guild.me or guild.get_member(self.bot.user.id)
        if not bot_member:
            print(f"Captcha: bot member is not available in guild {GUILD_ID}")
            return
        bot_perms = captcha_channel.permissions_for(bot_member)
        print(f"Captcha: Bot permissions - send_messages: {bot_perms.send_messages}, view_channel: {bot_perms.view_channel}")
        if not bot_perms.view_channel or not bot_perms.send_messages:
            print(f"Captcha: missing View Channel or Send Messages permission in {captcha_channel.id}")
            return
        
        # Delete previous bot messages in the channel
        try:
            async for message in captcha_channel.history(limit=50):
                if message.author == self.bot.user:
                    try:
                        await message.delete()
                        print(f"Captcha: Deleted old message {message.id}")
                    except:
                        pass
        except Exception as e:
            print(f"Captcha: Error cleaning old messages: {e}")
        
        # Create verification embed
        embed = discord.Embed(
            title="🔐 Server Verification System",
            description="**Welcome to Nightwish Trucking!** 🚛\n\n"
                       "To access all server channels and features, you need to complete verification.\n"
                       "Click the button below to start the verification process.",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="🛡️ Why Verification?",
            value="• Protects against spam and raids\n"
                  "• Ensures genuine community members\n"
                  "• Keeps our server safe and friendly",
            inline=True
        )
        
        embed.add_field(
            name="📝 Verification Process:",
            value="• Click 'Request Verification'\n"
                  "• Complete the captcha challenge\n"
                  "• Get instant access to the server\n"
                  "• Join our trucking community!",
            inline=True
        )
        
        embed.add_field(
            name="❓ Need Help?",
            value="If you're having trouble with verification, contact a staff member for assistance.\n **If its a question respond in small letters without any diacritics**",
            inline=False
        )
        
        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        embed.set_footer(text="Nightwish Trucking • Safe & Secure Community")
        
        # Send with persistent view
        view = VerificationRequestView()
        try:
            await captcha_channel.send(embed=embed, view=view)
            print("Captcha: Sent verification embed with button")
        except Exception as e:
            print(f"Captcha: Error sending verification embed: {e}")

    async def cog_load(self):
        """Called when the cog is loaded"""
        load_captcha_data()
        
        # Send verification embed after cog loads
        if self.captcha_enabled:
            # Add delay to ensure bot is fully ready
            await asyncio.sleep(3)
            
            try:
                await self.send_verification_embed()
                print("Captcha: Verification embed sent after cog load")
            except Exception as e:
                print(f"Captcha: Error sending embed after cog load: {e}")
                # Try again after 5 seconds
                await asyncio.sleep(5)
                try:
                    await self.send_verification_embed()
                    print("Captcha: Verification embed sent on retry after cog load")
                except Exception as e2:
                    print(f"Captcha: Failed to send embed on retry after cog load: {e2}")

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Handle new member joins - just log, verification embed stays permanent"""
        if member.guild.id != GUILD_ID or not self.captcha_enabled:
            return
        
        if member.bot:  # Skip bots
            return
        
        print(f"Captcha: New member joined: {member} ({member.id}) - they can use verification button")
        
        # Don't add any roles automatically - let them use the button when ready

    @commands.Cog.listener()
    async def on_message(self, message):
        """Handle captcha code submissions"""
        if message.author.bot:
            return
        
        if message.guild.id != GUILD_ID:
            return
        
        if message.channel.id != CAPTCHA_CHANNEL_ID:
            return
        
        user_id = message.author.id
        
        # Check if user has pending captcha
        if user_id not in _captcha_sessions:
            return
        
        session = _captcha_sessions[user_id]
        
        # Check if session expired
        if datetime.now() > session['expires']:
            await message.reply("❌ Your captcha challenge has expired. Please click 'New Challenge' to get a fresh one.")
            return
        
        # Check the answer based on challenge type
        submitted_answer = message.content.strip()
        challenge = session['challenge']
        correct_answer = challenge['answer']
        
        # Different validation based on challenge type
        if challenge['type'] in ['text', 'pattern']:
            # Case-sensitive for text and patterns
            is_correct = submitted_answer == correct_answer
        elif challenge['type'] == 'math':
            # Numeric answer
            is_correct = submitted_answer == correct_answer
        elif challenge['type'] == 'question':
            # Case-insensitive for questions
            is_correct = submitted_answer.lower() == correct_answer.lower()
        else:
            is_correct = submitted_answer.upper() == correct_answer.upper()
        
        if is_correct:
            # Successful verification
            guild = message.guild
            member = guild.get_member(user_id)
            
            if member:
                # Add verified role
                verified_role = guild.get_role(VERIFIED_ROLE_ID)
                if verified_role:
                    try:
                        await member.add_roles(verified_role, reason="Captcha verification successful")
                    except Exception as e:
                        print(f"Captcha: Error adding verified role: {e}")
                
                # Remove unverified role
                if UNVERIFIED_ROLE_ID:
                    unverified_role = guild.get_role(UNVERIFIED_ROLE_ID)
                    if unverified_role and unverified_role in member.roles:
                        try:
                            await member.remove_roles(unverified_role, reason="Verification complete")
                        except:
                            pass
                
                # Remove from sessions
                del _captcha_sessions[user_id]
                save_captcha_data()
                
                # Delete the captcha answer message (cleanup)
                try:
                    await message.delete()
                except:
                    pass
                
                print(f"Captcha: {member} verified successfully")
        else:
            # Wrong answer
            session['attempts'] += 1
            save_captcha_data()
            
            if session['attempts'] >= CAPTCHA_SETTINGS['max_attempts']:
                await message.reply("❌ Too many failed attempts. Please click 'New Challenge' to get a fresh verification.")
            else:
                remaining = CAPTCHA_SETTINGS['max_attempts'] - session['attempts']
                challenge_type = challenge['type']
                await message.reply(f"❌ Incorrect {challenge_type} answer. You have {remaining} attempts remaining.\n"
                                  f"*Hint: {challenge['description']}*")
            
            # Delete the wrong code message
            try:
                await message.delete()
            except:
                pass

async def setup(bot):
    # Add Captcha Cog
    await bot.add_cog(CaptchaCog(bot))
    print("Captcha: cog registered")
    
    # Create Captcha management command group
    class CaptchaGroup(discord.app_commands.Group):
        def __init__(self):
            super().__init__(name="captcha", description="Captcha system management commands")

        @discord.app_commands.command(name="toggle", description="Toggle captcha system on/off")
        @discord.app_commands.describe(enabled="Enable or disable the captcha system")
        async def toggle_captcha(self, interaction: discord.Interaction, enabled: bool = True):
            """Toggle captcha system"""
            if not has_admin_permissions(interaction.user):
                await interaction.response.send_message("❌ You need admin permissions to use this command.", ephemeral=True)
                return
            
            captcha_cog = bot.get_cog('CaptchaCog')
            if not captcha_cog:
                await interaction.response.send_message("❌ Captcha system not found.", ephemeral=True)
                return
            
            captcha_cog.captcha_enabled = enabled
            status = "enabled" if enabled else "disabled"
            await interaction.response.send_message(f"✅ Captcha system {status}.", ephemeral=True)

        @discord.app_commands.command(name="verify", description="Manually verify a user")
        @discord.app_commands.describe(user="User to verify")
        async def manual_verify(self, interaction: discord.Interaction, user: discord.Member):
            """Manually verify a user"""
            if not has_admin_permissions(interaction.user):
                await interaction.response.send_message("❌ You need admin permissions to use this command.", ephemeral=True)
                return
            
            guild = interaction.guild
            verified_role = guild.get_role(VERIFIED_ROLE_ID)
            
            if not verified_role:
                await interaction.response.send_message("❌ Verified role not found.", ephemeral=True)
                return
            
            try:
                # Add verified role
                await user.add_roles(verified_role, reason=f"Manually verified by {interaction.user}")
                
                # Remove unverified role
                if UNVERIFIED_ROLE_ID:
                    unverified_role = guild.get_role(UNVERIFIED_ROLE_ID)
                    if unverified_role and unverified_role in user.roles:
                        await user.remove_roles(unverified_role, reason="Manual verification")
                
                # Remove from captcha sessions
                if user.id in _captcha_sessions:
                    del _captcha_sessions[user.id]
                    save_captcha_data()
                
                await interaction.response.send_message(f"✅ {user.mention} has been manually verified.", ephemeral=True)
                
            except Exception as e:
                await interaction.response.send_message(f"❌ Error verifying user: {str(e)}", ephemeral=True)

        @discord.app_commands.command(name="refresh", description="Refresh the verification embed")
        async def refresh_embed(self, interaction: discord.Interaction):
            """Refresh the verification embed"""
            if not has_admin_permissions(interaction.user):
                await interaction.response.send_message("❌ You need admin permissions to use this command.", ephemeral=True)
                return
            
            captcha_cog = bot.get_cog('CaptchaCog')
            if not captcha_cog:
                await interaction.response.send_message("❌ Captcha system not found.", ephemeral=True)
                return
            
            await interaction.response.send_message("🔄 Refreshing verification embed...", ephemeral=True)
            await captcha_cog.send_verification_embed()
            await interaction.followup.send("✅ Verification embed refreshed!", ephemeral=True)

        @discord.app_commands.command(name="status", description="Show captcha system status")
        async def captcha_status(self, interaction: discord.Interaction):
            """Show captcha system status"""
            if not has_admin_permissions(interaction.user):
                await interaction.response.send_message("❌ You need admin permissions to use this command.", ephemeral=True)
                return
            
            captcha_cog = bot.get_cog('CaptchaCog')
            if not captcha_cog:
                await interaction.response.send_message("❌ Captcha system not found.", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="🔐 Captcha System Status",
                color=discord.Color.blue()
            )
            
            status = "🟢 Enabled" if captcha_cog.captcha_enabled else "🔴 Disabled"
            embed.add_field(name="System Status", value=status, inline=True)
            
            # Count pending verifications
            pending_count = len(_captcha_sessions)
            embed.add_field(name="Pending Verifications", value=str(pending_count), inline=True)
            
            # Channel info
            guild = interaction.guild
            captcha_channel = guild.get_channel(CAPTCHA_CHANNEL_ID)
            channel_info = captcha_channel.mention if captcha_channel else "Not found"
            embed.add_field(name="Captcha Channel", value=channel_info, inline=False)
            
            # Role info
            verified_role = guild.get_role(VERIFIED_ROLE_ID)
            role_info = verified_role.mention if verified_role else "Not found"
            embed.add_field(name="Verified Role", value=role_info, inline=True)
            
            if UNVERIFIED_ROLE_ID:
                unverified_role = guild.get_role(UNVERIFIED_ROLE_ID)
                unverified_info = unverified_role.mention if unverified_role else "Not found"
                embed.add_field(name="Unverified Role", value=unverified_info, inline=True)
            
            embed.set_footer(text="Use /captcha config to change settings")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)

        @discord.app_commands.command(name="config", description="Configure captcha settings")
        @app_commands.choices(
            difficulty=[
                app_commands.Choice(name="Easy", value="easy"),
                app_commands.Choice(name="Medium", value="medium"),
                app_commands.Choice(name="Hard", value="hard")
            ]
        )
        async def captcha_config(self, interaction: discord.Interaction, 
                               difficulty: app_commands.Choice[str] = None,
                               timeout_minutes: int = None,
                               max_attempts: int = None,
                               image_chance: int = None):
            if not has_admin_permissions(interaction.user):
                await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
                return
            
            changes = []
            
            if difficulty:
                CAPTCHA_SETTINGS['difficulty'] = difficulty.value
                changes.append(f"Difficulty: {difficulty.value.title()}")
            
            if timeout_minutes is not None:
                if 1 <= timeout_minutes <= 30:
                    CAPTCHA_SETTINGS['timeout_minutes'] = timeout_minutes
                    changes.append(f"Timeout: {timeout_minutes} minutes")
                else:
                    await interaction.response.send_message("❌ Timeout must be between 1 and 30 minutes.", ephemeral=True)
                    return
            
            if max_attempts is not None:
                if 1 <= max_attempts <= 10:
                    CAPTCHA_SETTINGS['max_attempts'] = max_attempts
                    changes.append(f"Max Attempts: {max_attempts}")
                else:
                    await interaction.response.send_message("❌ Max attempts must be between 1 and 10.", ephemeral=True)
                    return
            
            if image_chance is not None:
                if 0 <= image_chance <= 100:
                    CAPTCHA_SETTINGS['image_chance'] = image_chance / 100.0
                    changes.append(f"Image Chance: {image_chance}%")
                else:
                    await interaction.response.send_message("❌ Image chance must be between 0 and 100.", ephemeral=True)
                    return
            
            if not changes:
                # Show current settings
                embed = discord.Embed(
                    title="⚙️ Current Captcha Configuration",
                    color=discord.Color.blue()
                )
                
                settings_info = [
                    f"**Enabled Types:** {', '.join(CAPTCHA_SETTINGS['enabled_types'])}",
                    f"**Difficulty:** {CAPTCHA_SETTINGS['difficulty'].title()}",
                    f"**Image Chance:** {int(CAPTCHA_SETTINGS['image_chance'] * 100)}%",
                    f"**Timeout:** {CAPTCHA_SETTINGS['timeout_minutes']} minutes",
                    f"**Max Attempts:** {CAPTCHA_SETTINGS['max_attempts']}"
                ]
                
                embed.add_field(
                    name="Settings",
                    value="\n".join(settings_info),
                    inline=False
                )
                
                embed.set_footer(text="Use parameters to change settings")
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                embed = discord.Embed(
                    title="✅ Captcha Configuration Updated",
                    description=f"Updated by {interaction.user.mention}",
                    color=discord.Color.green()
                )
                
                embed.add_field(
                    name="Changes Made",
                    value="\n".join(f"• {change}" for change in changes),
                    inline=False
                )
                
                embed.set_footer(text="Settings applied immediately")
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
                print(f"Captcha: Settings updated by {interaction.user}: {', '.join(changes)}")

        @discord.app_commands.command(name="toggle_type", description="Toggle captcha challenge types")
        @app_commands.choices(
            challenge_type=[
                app_commands.Choice(name="Text Codes", value="text"),
                app_commands.Choice(name="Math Problems", value="math"),
                app_commands.Choice(name="Pattern Recognition", value="pattern"),
                app_commands.Choice(name="Knowledge Questions", value="question")
            ]
        )
        async def captcha_toggle_type(self, interaction: discord.Interaction, 
                                     challenge_type: app_commands.Choice[str]):
            if not has_admin_permissions(interaction.user):
                await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
                return
            
            type_value = challenge_type.value
            
            if type_value in CAPTCHA_SETTINGS['enabled_types']:
                if len(CAPTCHA_SETTINGS['enabled_types']) > 1:
                    CAPTCHA_SETTINGS['enabled_types'].remove(type_value)
                    status = "disabled"
                    color = discord.Color.red()
                else:
                    await interaction.response.send_message("❌ Cannot disable the last remaining challenge type.", ephemeral=True)
                    return
            else:
                CAPTCHA_SETTINGS['enabled_types'].append(type_value)
                status = "enabled"
                color = discord.Color.green()
            
            embed = discord.Embed(
                title=f"{'✅' if status == 'enabled' else '❌'} Challenge Type {status.title()}",
                description=f"{challenge_type.name} has been **{status}**",
                color=color
            )
            
            embed.add_field(
                name="Currently Enabled Types",
                value=", ".join(CAPTCHA_SETTINGS['enabled_types']),
                inline=False
            )
            
            embed.set_footer(text=f"Updated by {interaction.user.display_name}")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
            print(f"Captcha: Challenge type '{type_value}' {status} by {interaction.user}")

    # Add the command group to the bot
    bot.tree.add_command(CaptchaGroup())
    
    print("Captcha plugin loaded successfully")