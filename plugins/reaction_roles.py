"""
Reaction Roles Plugin for Discord Bot
Allows users to get/remove roles by reacting to embed messages
"""

import os
import json
import asyncio
import discord
from discord.ext import commands
from discord import app_commands

# Configuration
REACTION_ROLES_FILE = "plugins/reaction_roles.json"
GUILD_ID = 1168883480583745587
ADMIN_ROLE_ID = 1169176570150260776  # Adjust this to your admin role
DEV_ROLE_ID = 1347589804895768576   # Dev role ID

# Storage for reaction role configurations
_reaction_roles = {}

def load_reaction_roles():
    """Load reaction roles configuration from file"""
    global _reaction_roles
    try:
        if os.path.exists(REACTION_ROLES_FILE):
            with open(REACTION_ROLES_FILE, "r", encoding="utf-8") as f:
                _reaction_roles = json.load(f)
                print(f"ReactionRoles: Loaded {len(_reaction_roles)} configurations")
        else:
            _reaction_roles = {}
    except Exception as e:
        print(f"Failed to load reaction roles: {e}")
        _reaction_roles = {}

def save_reaction_roles():
    """Save reaction roles configuration to file"""
    try:
        os.makedirs(os.path.dirname(REACTION_ROLES_FILE), exist_ok=True)
        with open(REACTION_ROLES_FILE, "w", encoding="utf-8") as f:
            json.dump(_reaction_roles, f, ensure_ascii=False, indent=2)
        print(f"ReactionRoles: Saved {len(_reaction_roles)} configurations")
    except Exception as e:
        print(f"Failed to save reaction roles: {e}")

def has_admin_permissions(user):
    """Check if user has admin role or higher"""
    if not hasattr(user, 'roles'):
        return False
    
    role_ids = [role.id for role in user.roles]
    return (ADMIN_ROLE_ID in role_ids or 
            DEV_ROLE_ID in role_ids or
            any(role.name.lower() in ['admin', 'owner', 'developer'] for role in user.roles))

def create_role_embed(title, description, role_configs, image_url=None):
    """Create embed for reaction roles"""
    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.blue()
    )
    
    # Add image if provided
    if image_url:
        embed.set_image(url=image_url)
    
    role_list = []
    for config in role_configs:
        emoji = config['emoji']
        role_name = config['role_name']
        role_list.append(f"{emoji} - {role_name}")
    
    embed.add_field(
        name="Available Roles:",
        value="\n".join(role_list) if role_list else "No roles configured",
        inline=False
    )
    
    embed.add_field(
        name="How to use:",
        value="React with an emoji to get the corresponding role.\nReact again to remove the role.",
        inline=False
    )
    
    embed.set_footer(text="Nightwish Trucking • Reaction Roles")
    return embed

class ReactionRolesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        print("Reaction Roles plugin initialized")

    async def cog_load(self):
        """Called when the cog is loaded"""
        load_reaction_roles()

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        """Handle reaction additions"""
        if payload.user_id == self.bot.user.id:
            return
        
        message_key = f"{payload.channel_id}_{payload.message_id}"
        if message_key not in _reaction_roles:
            return
        
        config = _reaction_roles[message_key]
        
        # Find matching emoji and role
        for role_config in config['roles']:
            if str(payload.emoji) == role_config['emoji']:
                guild = self.bot.get_guild(payload.guild_id)
                if not guild:
                    return
                
                member = guild.get_member(payload.user_id)
                role = guild.get_role(role_config['role_id'])
                
                if member and role:
                    try:
                        if role not in member.roles:
                            await member.add_roles(role, reason="Reaction role assignment")
                            print(f"ReactionRoles: Added role {role.name} to {member.display_name}")
                        
                        # Try to send DM confirmation
                        try:
                            embed = discord.Embed(
                                title="✅ Role Added",
                                description=f"You've been given the **{role.name}** role in {guild.name}!",
                                color=discord.Color.green()
                            )
                            await member.send(embed=embed)
                        except discord.Forbidden:
                            pass  # User has DMs disabled
                            
                    except discord.Forbidden:
                        print(f"ReactionRoles: No permission to add role {role.name} to {member.display_name}")
                    except Exception as e:
                        print(f"ReactionRoles: Error adding role: {e}")
                break

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        """Handle reaction removals"""
        if payload.user_id == self.bot.user.id:
            return
        
        message_key = f"{payload.channel_id}_{payload.message_id}"
        if message_key not in _reaction_roles:
            return
        
        config = _reaction_roles[message_key]
        
        # Find matching emoji and role
        for role_config in config['roles']:
            if str(payload.emoji) == role_config['emoji']:
                guild = self.bot.get_guild(payload.guild_id)
                if not guild:
                    return
                
                member = guild.get_member(payload.user_id)
                role = guild.get_role(role_config['role_id'])
                
                if member and role:
                    try:
                        if role in member.roles:
                            await member.remove_roles(role, reason="Reaction role removal")
                            print(f"ReactionRoles: Removed role {role.name} from {member.display_name}")
                        
                        # Try to send DM confirmation
                        try:
                            embed = discord.Embed(
                                title="❌ Role Removed",
                                description=f"The **{role.name}** role has been removed from you in {guild.name}.",
                                color=discord.Color.red()
                            )
                            await member.send(embed=embed)
                        except discord.Forbidden:
                            pass  # User has DMs disabled
                            
                    except discord.Forbidden:
                        print(f"ReactionRoles: No permission to remove role {role.name} from {member.display_name}")
                    except Exception as e:
                        print(f"ReactionRoles: Error removing role: {e}")
                break

def setup(bot):
    # Add Reaction Roles Cog
    asyncio.create_task(bot.add_cog(ReactionRolesCog(bot)))
    
    # Create Reaction Roles command group
    class ReactionRolesGroup(discord.app_commands.Group):
        def __init__(self):
            super().__init__(name="roles", description="Reaction roles management commands")

        @discord.app_commands.command(name="create", description="Create a new reaction roles embed")
        @discord.app_commands.describe(
            channel="Channel to send the embed to",
            title="Title for the embed",
            description="Description for the embed",
            image_url="Image URL for the embed (optional)"
        )
        async def create_embed(self, interaction: discord.Interaction, 
                             channel: discord.TextChannel, 
                             title: str, 
                             description: str = "React to get roles!",
                             image_url: str = None):
            """Create a new reaction roles embed"""
            if not has_admin_permissions(interaction.user):
                await interaction.response.send_message("❌ You need admin permissions to use this command.", ephemeral=True)
                return
            
            # Create embed with placeholder
            embed = create_role_embed(title, description, [], image_url)
            
            try:
                message = await channel.send(embed=embed)
                
                # Store configuration
                message_key = f"{channel.id}_{message.id}"
                _reaction_roles[message_key] = {
                    "channel_id": channel.id,
                    "message_id": message.id,
                    "title": title,
                    "description": description,
                    "image_url": image_url,
                    "roles": []
                }
                save_reaction_roles()
                
                await interaction.response.send_message(
                    f"✅ Reaction roles embed created in {channel.mention}!\n"
                    f"Message ID: `{message.id}`\n"
                    f"Use `/roles add` to add roles to this embed.",
                    ephemeral=True
                )
                
            except discord.Forbidden:
                await interaction.response.send_message(f"❌ I don't have permission to send messages in {channel.mention}.", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"❌ Error creating embed: {str(e)}", ephemeral=True)

        @discord.app_commands.command(name="add", description="Add a role to a reaction roles embed")
        @discord.app_commands.describe(
            message_id="ID of the reaction roles message",
            emoji="Emoji for the reaction",
            role="Role to assign"
        )
        async def add_role(self, interaction: discord.Interaction, 
                          message_id: str, 
                          emoji: str, 
                          role: discord.Role):
            """Add a role to an existing reaction roles embed"""
            if not has_admin_permissions(interaction.user):
                await interaction.response.send_message("❌ You need admin permissions to use this command.", ephemeral=True)
                return
            
            # Find the message configuration
            message_key = None
            for key, config in _reaction_roles.items():
                if str(config['message_id']) == message_id:
                    message_key = key
                    break
            
            if not message_key:
                await interaction.response.send_message("❌ Message ID not found in reaction roles configurations.", ephemeral=True)
                return
            
            config = _reaction_roles[message_key]
            
            # Check if emoji or role already exists
            for existing_role in config['roles']:
                if existing_role['emoji'] == emoji:
                    await interaction.response.send_message(f"❌ Emoji {emoji} is already used in this embed.", ephemeral=True)
                    return
                if existing_role['role_id'] == role.id:
                    await interaction.response.send_message(f"❌ Role {role.mention} is already in this embed.", ephemeral=True)
                    return
            
            # Add role configuration
            config['roles'].append({
                "emoji": emoji,
                "role_id": role.id,
                "role_name": role.name
            })
            save_reaction_roles()
            
            # Update the embed
            try:
                channel = interaction.guild.get_channel(config['channel_id'])
                message = await channel.fetch_message(config['message_id'])
                
                # Create updated embed
                updated_embed = create_role_embed(config['title'], config['description'], config['roles'], config.get('image_url'))
                await message.edit(embed=updated_embed)
                
                # Add reaction to message
                await message.add_reaction(emoji)
                
                await interaction.response.send_message(
                    f"✅ Added role {role.mention} with emoji {emoji} to the reaction roles embed!",
                    ephemeral=True
                )
                
            except discord.NotFound:
                await interaction.response.send_message("❌ Message not found. It may have been deleted.", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("❌ I don't have permission to edit that message or add reactions.", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"❌ Error updating embed: {str(e)}", ephemeral=True)

        @discord.app_commands.command(name="remove", description="Remove a role from a reaction roles embed")
        @discord.app_commands.describe(
            message_id="ID of the reaction roles message",
            emoji="Emoji to remove"
        )
        async def remove_role(self, interaction: discord.Interaction, 
                            message_id: str, 
                            emoji: str):
            """Remove a role from an existing reaction roles embed"""
            if not has_admin_permissions(interaction.user):
                await interaction.response.send_message("❌ You need admin permissions to use this command.", ephemeral=True)
                return
            
            # Find the message configuration
            message_key = None
            for key, config in _reaction_roles.items():
                if str(config['message_id']) == message_id:
                    message_key = key
                    break
            
            if not message_key:
                await interaction.response.send_message("❌ Message ID not found in reaction roles configurations.", ephemeral=True)
                return
            
            config = _reaction_roles[message_key]
            
            # Find and remove the role
            role_to_remove = None
            for i, role_config in enumerate(config['roles']):
                if role_config['emoji'] == emoji:
                    role_to_remove = config['roles'].pop(i)
                    break
            
            if not role_to_remove:
                await interaction.response.send_message(f"❌ Emoji {emoji} not found in this embed.", ephemeral=True)
                return
            
            save_reaction_roles()
            
            # Update the embed
            try:
                channel = interaction.guild.get_channel(config['channel_id'])
                message = await channel.fetch_message(config['message_id'])
                
                # Create updated embed
                updated_embed = create_role_embed(config['title'], config['description'], config['roles'], config.get('image_url'))
                await message.edit(embed=updated_embed)
                
                # Remove reaction from message
                await message.clear_reaction(emoji)
                
                await interaction.response.send_message(
                    f"✅ Removed role **{role_to_remove['role_name']}** with emoji {emoji} from the reaction roles embed!",
                    ephemeral=True
                )
                
            except discord.NotFound:
                await interaction.response.send_message("❌ Message not found. It may have been deleted.", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("❌ I don't have permission to edit that message or manage reactions.", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"❌ Error updating embed: {str(e)}", ephemeral=True)

        @discord.app_commands.command(name="list", description="List all reaction roles configurations")
        async def list_configs(self, interaction: discord.Interaction):
            """List all reaction roles configurations"""
            if not has_admin_permissions(interaction.user):
                await interaction.response.send_message("❌ You need admin permissions to use this command.", ephemeral=True)
                return
            
            if not _reaction_roles:
                await interaction.response.send_message("✅ No reaction roles configurations found.", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="📋 Reaction Roles Configurations",
                color=discord.Color.blue()
            )
            
            for key, config in _reaction_roles.items():
                channel = interaction.guild.get_channel(config['channel_id'])
                channel_mention = channel.mention if channel else "Unknown Channel"
                
                roles_text = []
                for role_config in config['roles']:
                    role = interaction.guild.get_role(role_config['role_id'])
                    role_name = role.name if role else role_config['role_name']
                    roles_text.append(f"{role_config['emoji']} {role_name}")
                
                image_info = f"**Image:** {config.get('image_url', 'None')}\n" if config.get('image_url') else ""
                embed.add_field(
                    name=f"📌 {config['title']}",
                    value=f"**Channel:** {channel_mention}\n"
                          f"**Message ID:** `{config['message_id']}`\n"
                          f"{image_info}"
                          f"**Roles:** {', '.join(roles_text) if roles_text else 'None'}",
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)

        @discord.app_commands.command(name="image", description="Set or update image for a reaction roles embed")
        @discord.app_commands.describe(
            message_id="ID of the reaction roles message",
            image_url="Image URL for the embed (leave empty to remove image)"
        )
        async def set_image(self, interaction: discord.Interaction, 
                           message_id: str, 
                           image_url: str = None):
            """Set or update image for an existing reaction roles embed"""
            if not has_admin_permissions(interaction.user):
                await interaction.response.send_message("❌ You need admin permissions to use this command.", ephemeral=True)
                return
            
            # Find the message configuration
            message_key = None
            for key, config in _reaction_roles.items():
                if str(config['message_id']) == message_id:
                    message_key = key
                    break
            
            if not message_key:
                await interaction.response.send_message("❌ Message ID not found in reaction roles configurations.", ephemeral=True)
                return
            
            config = _reaction_roles[message_key]
            
            # Update image URL
            config['image_url'] = image_url
            save_reaction_roles()
            
            # Update the embed
            try:
                channel = interaction.guild.get_channel(config['channel_id'])
                message = await channel.fetch_message(config['message_id'])
                
                # Create updated embed
                updated_embed = create_role_embed(config['title'], config['description'], config['roles'], config.get('image_url'))
                await message.edit(embed=updated_embed)
                
                if image_url:
                    await interaction.response.send_message(
                        f"✅ Updated image for reaction roles embed!",
                        ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        f"✅ Removed image from reaction roles embed!",
                        ephemeral=True
                    )
                
            except discord.NotFound:
                await interaction.response.send_message("❌ Message not found. It may have been deleted.", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("❌ I don't have permission to edit that message.", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"❌ Error updating embed: {str(e)}", ephemeral=True)

        @discord.app_commands.command(name="delete", description="Delete a reaction roles embed configuration")
        @discord.app_commands.describe(message_id="ID of the reaction roles message to delete")
        async def delete_config(self, interaction: discord.Interaction, message_id: str):
            """Delete a reaction roles configuration"""
            if not has_admin_permissions(interaction.user):
                await interaction.response.send_message("❌ You need admin permissions to use this command.", ephemeral=True)
                return
            
            # Find and remove the configuration
            message_key = None
            for key, config in _reaction_roles.items():
                if str(config['message_id']) == message_id:
                    message_key = key
                    break
            
            if not message_key:
                await interaction.response.send_message("❌ Message ID not found in reaction roles configurations.", ephemeral=True)
                return
            
            config = _reaction_roles.pop(message_key)
            save_reaction_roles()
            
            await interaction.response.send_message(
                f"✅ Deleted reaction roles configuration for message `{message_id}`.\n"
                f"**Note:** The message itself was not deleted - only the configuration.",
                ephemeral=True
            )

    # Add the command group to the bot
    bot.tree.add_command(ReactionRolesGroup())
    
    print("Reaction Roles plugin loaded successfully")