import discord
from discord.ext import commands
from discord import app_commands
import re
import asyncio
import os

# Configuration
GUILD_ID = 1168883480583745587
try:
    env_gid = os.environ.get('GUILD_ID')
    if env_gid and str(env_gid).strip().isdigit():
        GUILD_ID = int(env_gid)
        print(f"SendMessage: using global GUILD_ID from environment: {GUILD_ID}")
except Exception:
    pass
ADMIN_ROLE_ID = 1169176570150260776
DEV_ROLE_ID = 1347589804895768576

def has_admin_permissions(user):
    """Check if user has admin permissions"""
    if not user.guild:
        return False
    
    role_ids = [role.id for role in user.roles]
    return (user.guild_permissions.administrator or
            ADMIN_ROLE_ID in role_ids or
            DEV_ROLE_ID in role_ids or
            any(role.name.lower() in ['admin', 'owner', 'developer'] for role in user.roles))

def process_custom_emojis(message_content, guild):
    """Process custom emojis in message content"""
    # Pattern for custom emoji names like :emoji_name:
    emoji_pattern = r':([a-zA-Z0-9_]+):'
    
    def replace_emoji(match):
        emoji_name = match.group(1)
        # Find emoji in guild
        for emoji in guild.emojis:
            if emoji.name.lower() == emoji_name.lower():
                return str(emoji)
        # If not found, return original
        return match.group(0)
    
    return re.sub(emoji_pattern, replace_emoji, message_content)

class SendMessageCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="sendmsg", description="Send a message to a specific channel")
    @app_commands.describe(
        channel="The channel to send the message to",
        message="The message content (supports Markdown and server emojis) - OPTIONAL if using file",
        file="Text file to upload and send as message (overrides message parameter)"
    )
    async def send_to_channel(self, interaction: discord.Interaction, 
                            channel: discord.TextChannel, 
                            message: str = None,
                            file: discord.Attachment = None):
        if not has_admin_permissions(interaction.user):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return
        
        # Check if bot has permissions in target channel
        bot_permissions = channel.permissions_for(interaction.guild.me)
        if not bot_permissions.send_messages:
            await interaction.response.send_message(
                f"❌ I don't have permission to send messages in {channel.mention}.", 
                ephemeral=True
            )
            return
        
        # Determine message content - file takes priority
        if file:
            # Check if file is a text file
            if not file.filename.lower().endswith(('.txt', '.md', '.text')):
                await interaction.response.send_message(
                    "❌ Only text files (.txt, .md, .text) are supported.", 
                    ephemeral=True
                )
                return
            
            # Check file size (Discord limit is 25MB, but we'll be more restrictive for text)
            if file.size > 1024 * 1024:  # 1MB limit for text files
                await interaction.response.send_message(
                    "❌ File is too large. Maximum size is 1MB for text files.", 
                    ephemeral=True
                )
                return
            
            try:
                # Download and read the file
                file_content = await file.read()
                message_content = file_content.decode('utf-8')
                
                # Check Discord message length limit (2000 characters)
                if len(message_content) > 2000:
                    await interaction.response.send_message(
                        f"❌ File content is too long ({len(message_content)} characters). Discord limit is 2000 characters.", 
                        ephemeral=True
                    )
                    return
                    
            except UnicodeDecodeError:
                await interaction.response.send_message(
                    "❌ File must be valid UTF-8 text.", 
                    ephemeral=True
                )
                return
            except Exception as e:
                await interaction.response.send_message(
                    f"❌ Error reading file: {str(e)}", 
                    ephemeral=True
                )
                return
        
        elif message:
            message_content = message
        else:
            await interaction.response.send_message(
                "❌ You must provide either a message or upload a text file.", 
                ephemeral=True
            )
            return
        
        # Process custom emojis
        processed_message = process_custom_emojis(message_content, interaction.guild)
        
        try:
            # Send the message
            sent_message = await channel.send(processed_message)
            
            # Confirmation embed
            embed = discord.Embed(
                title="✅ Message Sent Successfully",
                color=discord.Color.green()
            )
            
            embed.add_field(
                name="Channel",
                value=channel.mention,
                inline=True
            )
            
            embed.add_field(
                name="Message ID",
                value=f"`{sent_message.id}`",
                inline=True
            )
            
            # Show preview of message (truncated if too long)
            preview = processed_message[:200] + "..." if len(processed_message) > 200 else processed_message
            embed.add_field(
                name="Content Preview",
                value=f"```\n{preview}\n```",
                inline=False
            )
            
            # Add file info if message came from file
            if file:
                embed.add_field(
                    name="Source File",
                    value=f"📄 `{file.filename}` ({file.size} bytes)\n{len(message_content)} characters",
                    inline=True
                )
            
            embed.add_field(
                name="Message Link",
                value=f"[Jump to Message]({sent_message.jump_url})",
                inline=False
            )
            
            embed.set_footer(text=f"Sent by {interaction.user.display_name}")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
            print(f"SendMsg: {interaction.user} sent message to #{channel.name}: {processed_message[:50]}...")
            
        except discord.Forbidden:
            await interaction.response.send_message(
                f"❌ I don't have permission to send messages in {channel.mention}.", 
                ephemeral=True
            )
        except discord.HTTPException as e:
            await interaction.response.send_message(
                f"❌ Error sending message: {str(e)}", 
                ephemeral=True
            )

    @app_commands.command(name="sendfile", description="Send a text file as multiple messages (for long content)")
    @app_commands.describe(
        channel="The channel to send the messages to",
        file="Text file to upload and send (will split into multiple messages if needed)",
        split_by="How to split long content"
    )
    @app_commands.choices(split_by=[
        app_commands.Choice(name="Lines (every 20 lines)", value="lines"),
        app_commands.Choice(name="Characters (every 1900 chars)", value="chars"),
        app_commands.Choice(name="Paragraphs (empty lines)", value="paragraphs")
    ])
    async def send_file_split(self, interaction: discord.Interaction,
                             channel: discord.TextChannel,
                             file: discord.Attachment,
                             split_by: app_commands.Choice[str] = None):
        if not has_admin_permissions(interaction.user):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return
        
        # Check bot permissions
        bot_permissions = channel.permissions_for(interaction.guild.me)
        if not bot_permissions.send_messages:
            await interaction.response.send_message(
                f"❌ I don't have permission to send messages in {channel.mention}.", 
                ephemeral=True
            )
            return
        
        # Check file type
        if not file.filename.lower().endswith(('.txt', '.md', '.text')):
            await interaction.response.send_message(
                "❌ Only text files (.txt, .md, .text) are supported.", 
                ephemeral=True
            )
            return
        
        # Check file size (5MB limit for split files)
        if file.size > 5 * 1024 * 1024:
            await interaction.response.send_message(
                "❌ File is too large. Maximum size is 5MB for split files.", 
                ephemeral=True
            )
            return
        
        try:
            # Download and read the file
            file_content = await file.read()
            content = file_content.decode('utf-8')
            
        except UnicodeDecodeError:
            await interaction.response.send_message(
                "❌ File must be valid UTF-8 text.", 
                ephemeral=True
            )
            return
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error reading file: {str(e)}", 
                ephemeral=True
            )
            return
        
        # Process custom emojis
        processed_content = process_custom_emojis(content, interaction.guild)
        
        # Split content based on method
        split_method = split_by.value if split_by else "chars"
        
        if split_method == "lines":
            lines = processed_content.split('\n')
            chunks = []
            current_chunk = []
            line_count = 0
            
            for line in lines:
                current_chunk.append(line)
                line_count += 1
                
                # Check if chunk would exceed Discord limit or line limit
                chunk_text = '\n'.join(current_chunk)
                if len(chunk_text) > 1900 or line_count >= 20:
                    if current_chunk:
                        chunks.append(chunk_text)
                        current_chunk = []
                        line_count = 0
            
            # Add remaining lines
            if current_chunk:
                chunks.append('\n'.join(current_chunk))
                
        elif split_method == "paragraphs":
            paragraphs = processed_content.split('\n\n')
            chunks = []
            current_chunk = []
            
            for paragraph in paragraphs:
                test_chunk = '\n\n'.join(current_chunk + [paragraph])
                if len(test_chunk) > 1900 and current_chunk:
                    chunks.append('\n\n'.join(current_chunk))
                    current_chunk = [paragraph]
                else:
                    current_chunk.append(paragraph)
            
            # Add remaining paragraphs
            if current_chunk:
                chunks.append('\n\n'.join(current_chunk))
                
        else:  # chars
            chunks = []
            for i in range(0, len(processed_content), 1900):
                chunks.append(processed_content[i:i+1900])
        
        # Send chunks
        if not chunks:
            await interaction.response.send_message("❌ File appears to be empty.", ephemeral=True)
            return
        
        # Initial response
        embed = discord.Embed(
            title="📤 Sending File Content",
            description=f"Sending `{file.filename}` as {len(chunks)} message(s) to {channel.mention}",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="File Info",
            value=f"📄 Size: {file.size} bytes\n📝 Characters: {len(content)}\n🔀 Split method: {split_method}",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Send each chunk
        sent_messages = []
        for i, chunk in enumerate(chunks, 1):
            try:
                if i == 1:
                    # First message with file info
                    msg = await channel.send(f"📄 **{file.filename}** (Part {i}/{len(chunks)})\n```\n{chunk}\n```")
                else:
                    msg = await channel.send(f"📄 **{file.filename}** (Part {i}/{len(chunks)})\n```\n{chunk}\n```")
                sent_messages.append(msg)
                
                # Small delay between messages
                await asyncio.sleep(0.5)
                
            except discord.HTTPException as e:
                await interaction.followup.send(f"❌ Error sending part {i}: {str(e)}", ephemeral=True)
                break
        
        # Final confirmation
        success_embed = discord.Embed(
            title="✅ File Sent Successfully",
            description=f"Sent {len(sent_messages)}/{len(chunks)} message(s) to {channel.mention}",
            color=discord.Color.green()
        )
        
        if sent_messages:
            success_embed.add_field(
                name="First Message Link",
                value=f"[Jump to First Message]({sent_messages[0].jump_url})",
                inline=False
            )
        
        success_embed.set_footer(text=f"Sent by {interaction.user.display_name}")
        
        await interaction.followup.send(embed=success_embed, ephemeral=True)
        
        print(f"SendMsg: {interaction.user} sent file {file.filename} as {len(sent_messages)} messages to #{channel.name}")

async def setup(bot):
    """Setup function for the plugin"""
    await bot.add_cog(SendMessageCog(bot))
    print("Send Message plugin loaded successfully")