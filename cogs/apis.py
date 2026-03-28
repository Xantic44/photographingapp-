"""
External APIs cog - Integrates various third-party APIs.
Consolidated into command groups to reduce slash command count.
"""
import os
import random
from datetime import datetime, timezone
from typing import Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from core.helpers import Colors, logger


class APIs(commands.Cog):
    """External API integrations for enhanced bot functionality."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session: Optional[aiohttp.ClientSession] = None
        
        # API Keys from environment
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.steam_key = os.getenv("STEAM_API_KEY")
        self.weather_key = os.getenv("OPENWEATHER_API_KEY")
        self.giphy_key = os.getenv("GIPHY_API_KEY")
        self.wolfram_key = os.getenv("WOLFRAM_API_KEY")
        self.gemini_key = os.getenv("GEMINI_API_KEY")
        
        # Rate limiting
        self._ai_cooldowns: dict[str, float] = {}
        
    async def cog_load(self):
        """Create aiohttp session on cog load."""
        self.session = aiohttp.ClientSession()
        
    async def cog_unload(self):
        """Close aiohttp session on cog unload."""
        if self.session:
            await self.session.close()

    def _check_cooldown(self, key: str, seconds: int = 10) -> float | None:
        """Check cooldown, returns remaining seconds or None if ready."""
        now = datetime.now(timezone.utc).timestamp()
        if key in self._ai_cooldowns:
            remaining = self._ai_cooldowns[key] - now
            if remaining > 0:
                return remaining
        self._ai_cooldowns[key] = now + seconds
        return None

    # ═══════════════════════════════════════════════════════════════════════
    #                            AI GROUP
    # ═══════════════════════════════════════════════════════════════════════
    
    ai_group = app_commands.Group(name="ai", description="AI assistants (ChatGPT, Gemini)")

    @ai_group.command(name="gpt", description="🤖 Ask ChatGPT a question")
    @app_commands.describe(question="Your question for ChatGPT")
    async def ai_gpt(self, interaction: discord.Interaction, question: str):
        # Ensure session is open
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession()
        """Ask ChatGPT a question."""
        if not self.openai_key:
            await interaction.response.send_message(
                "❌ OpenAI API key not configured. Add `OPENAI_API_KEY` to .env",
                ephemeral=True
            )
            return
        
        remaining = self._check_cooldown(f"gpt_{interaction.user.id}")
        if remaining:
            await interaction.response.send_message(f"⏳ Wait {remaining:.1f}s", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        try:
            headers = {"Authorization": f"Bearer {self.openai_key}", "Content-Type": "application/json"}
            payload = {
                "model": "gpt-3.5-turbo",
                "messages": [
                    {"role": "system", "content": "You are a helpful Discord bot. Keep responses under 1500 chars."},
                    {"role": "user", "content": question}
                ],
                "max_tokens": 500,
                "temperature": 0.7
            }
            
            async with self.session.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=30) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    answer = data["choices"][0]["message"]["content"]
                    embed = discord.Embed(title="🤖 ChatGPT", description=answer[:4000], color=Colors.INFO)
                    embed.set_footer(text=f"Asked by {interaction.user.display_name}")
                    await interaction.followup.send(embed=embed)
                else:
                    await interaction.followup.send(f"❌ API error: {resp.status}")
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {str(e)[:100]}")
            logger.error(f"GPT error: {e}")

    @ai_group.command(name="gemini", description="✨ Ask Google Gemini a question")
    @app_commands.describe(question="Your question for Gemini")
    async def ai_gemini(self, interaction: discord.Interaction, question: str):
        # Ensure session is open
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession()
        """Ask Google Gemini a question."""
        if not self.gemini_key:
            await interaction.response.send_message(
                "❌ Gemini API key not configured. Get free key: https://makersuite.google.com/app/apikey",
                ephemeral=True
            )
            return
        
        remaining = self._check_cooldown(f"gemini_{interaction.user.id}")
        if remaining:
            await interaction.response.send_message(f"⏳ Wait {remaining:.1f}s", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={self.gemini_key}"
            payload = {"contents": [{"parts": [{"text": question}]}], "generationConfig": {"maxOutputTokens": 1000}}
            
            async with self.session.post(url, json=payload, timeout=30) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    candidates = data.get("candidates", [])
                    answer = "No response."
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            answer = parts[0].get("text", "No response.")
                    embed = discord.Embed(title="✨ Gemini", description=answer[:4000], color=Colors.INFO)
                    embed.set_footer(text=f"Asked by {interaction.user.display_name}")
                    await interaction.followup.send(embed=embed)
                else:
                    await interaction.followup.send(f"❌ API error: {resp.status}")
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {str(e)[:100]}")
            logger.error(f"Gemini error: {e}")

    # ═══════════════════════════════════════════════════════════════════════
    #                         STANDALONE COMMANDS
    # ═══════════════════════════════════════════════════════════════════════

    @app_commands.command(name="wiki", description="📚 Search Wikipedia")
    @app_commands.describe(query="What to search for")
    async def wiki(self, interaction: discord.Interaction, query: str):
        # Ensure session is open
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession()
        """Search Wikipedia and return a summary."""
        await interaction.response.defer()
        try:
            search_url = "https://en.wikipedia.org/w/api.php"
            params = {"action": "query", "list": "search", "srsearch": query, "format": "json", "srlimit": 1}
            
            async with self.session.get(search_url, params=params, timeout=15) as resp:
                if resp.status != 200:
                    await interaction.followup.send("❌ Wikipedia search failed.")
                    return
                data = await resp.json()
                results = data.get("query", {}).get("search", [])
                if not results:
                    await interaction.followup.send(f"❌ No article found for '{query}'")
                    return
                title = results[0]["title"]
            
            summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{title.replace(' ', '_')}"
            async with self.session.get(summary_url, timeout=15) as resp:
                if resp.status != 200:
                    await interaction.followup.send("❌ Failed to fetch article.")
                    return
                data = await resp.json()
                embed = discord.Embed(
                    title=f"📚 {data.get('title', title)}",
                    description=data.get("extract", "No summary.")[:2000],
                    url=data.get("content_urls", {}).get("desktop", {}).get("page"),
                    color=Colors.INFO
                )
                if data.get("thumbnail"):
                    embed.set_thumbnail(url=data["thumbnail"]["source"])
                embed.set_footer(text="Source: Wikipedia")
                await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {str(e)[:100]}")

    @app_commands.command(name="weather", description="🌤️ Get current weather")
    @app_commands.describe(location="City name (e.g., 'London' or 'New York, US')")
    async def weather(self, interaction: discord.Interaction, location: str):
        # Ensure session is open
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession()
        """Get current weather using OpenWeatherMap."""
        if not self.weather_key:
            await interaction.response.send_message("❌ Weather API key not configured.", ephemeral=True)
            return
        
        await interaction.response.defer()
        try:
            url = "https://api.openweathermap.org/data/2.5/weather"
            params = {"q": location, "appid": self.weather_key, "units": "metric"}
            
            async with self.session.get(url, params=params, timeout=15) as resp:
                if resp.status == 404:
                    await interaction.followup.send(f"❌ Location '{location}' not found.")
                    return
                if resp.status != 200:
                    await interaction.followup.send(f"❌ API error: {resp.status}")
                    return
                
                data = await resp.json()
                temp = data["main"]["temp"]
                feels = data["main"]["feels_like"]
                humidity = data["main"]["humidity"]
                desc = data["weather"][0]["description"].title()
                icon = data["weather"][0]["icon"]
                wind = data["wind"]["speed"]
                
                emojis = {"01": "☀️", "02": "⛅", "03": "☁️", "04": "☁️", "09": "🌧️", "10": "🌦️", "11": "⛈️", "13": "🌨️", "50": "🌫️"}
                emoji = emojis.get(icon[:2], "🌡️")
                
                embed = discord.Embed(
                    title=f"{emoji} {data['name']}, {data['sys']['country']}",
                    description=f"**{desc}**",
                    color=Colors.INFO
                )
                embed.add_field(name="🌡️ Temp", value=f"{temp:.1f}°C", inline=True)
                embed.add_field(name="🤒 Feels", value=f"{feels:.1f}°C", inline=True)
                embed.add_field(name="💧 Humidity", value=f"{humidity}%", inline=True)
                embed.add_field(name="💨 Wind", value=f"{wind} m/s", inline=True)
                embed.set_thumbnail(url=f"https://openweathermap.org/img/wn/{icon}@2x.png")
                await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {str(e)[:100]}")

    @app_commands.command(name="crypto", description="💰 Get cryptocurrency price")
    @app_commands.describe(coin="Coin name (bitcoin, ethereum, etc.)")
    async def crypto(self, interaction: discord.Interaction, coin: str):
        """Get crypto prices from CoinGecko (free, no key)."""
        await interaction.response.defer()
        try:
            url = "https://api.coingecko.com/api/v3/coins/markets"
            params = {"vs_currency": "usd", "ids": coin.lower(), "sparkline": "false", "price_change_percentage": "24h,7d"}
            
            async with self.session.get(url, params=params, timeout=15) as resp:
                if resp.status != 200:
                    # Try search
                    async with self.session.get("https://api.coingecko.com/api/v3/search", params={"query": coin}, timeout=15) as sr:
                        if sr.status == 200:
                            sd = await sr.json()
                            coins = sd.get("coins", [])
                            if coins:
                                params["ids"] = coins[0]["id"]
                                async with self.session.get(url, params=params, timeout=15) as rr:
                                    data = await rr.json() if rr.status == 200 else []
                            else:
                                await interaction.followup.send(f"❌ Coin '{coin}' not found.")
                                return
                        else:
                            await interaction.followup.send("❌ CoinGecko API error.")
                            return
                else:
                    data = await resp.json()
                
                if not data:
                    await interaction.followup.send(f"❌ No data for '{coin}'")
                    return
                
                c = data[0]
                change = c.get("price_change_percentage_24h", 0) or 0
                emoji = "🟢" if change >= 0 else "🔴"
                
                embed = discord.Embed(
                    title=f"💰 {c['name']} ({c['symbol'].upper()})",
                    color=Colors.SUCCESS if change >= 0 else Colors.ERROR
                )
                embed.add_field(name="💵 Price", value=f"${c['current_price']:,.2f}", inline=True)
                embed.add_field(name=f"{emoji} 24h", value=f"{change:+.2f}%", inline=True)
                if c.get("market_cap"):
                    embed.add_field(name="📈 Cap", value=f"${c['market_cap']:,.0f}", inline=True)
                if c.get("image"):
                    embed.set_thumbnail(url=c["image"])
                embed.set_footer(text="CoinGecko")
                await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {str(e)[:100]}")

    @app_commands.command(name="gif", description="🎬 Search for a GIF")
    @app_commands.describe(query="What kind of GIF")
    async def gif(self, interaction: discord.Interaction, query: str):
        """Search for a GIF on Giphy."""
        if not self.giphy_key:
            await interaction.response.send_message("❌ Giphy API key not configured.", ephemeral=True)
            return
        
        await interaction.response.defer()
        try:
            url = "https://api.giphy.com/v1/gifs/search"
            params = {"api_key": self.giphy_key, "q": query, "limit": 10, "rating": "pg-13"}
            
            async with self.session.get(url, params=params, timeout=15) as resp:
                if resp.status != 200:
                    await interaction.followup.send("❌ Giphy API error.")
                    return
                data = await resp.json()
                gifs = data.get("data", [])
                if not gifs:
                    await interaction.followup.send(f"❌ No GIFs for '{query}'")
                    return
                gif_url = random.choice(gifs)["images"]["original"]["url"]
                embed = discord.Embed(title=f"🎬 {query}", color=Colors.INFO)
                embed.set_image(url=gif_url)
                embed.set_footer(text="Giphy")
                await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {str(e)[:100]}")

    @app_commands.command(name="calc", description="🔢 Calculate with Wolfram Alpha")
    @app_commands.describe(query="Math or question (e.g., 'integrate x^2')")
    async def calc(self, interaction: discord.Interaction, query: str):
        """Query Wolfram Alpha."""
        if not self.wolfram_key:
            await interaction.response.send_message("❌ Wolfram API key not configured.", ephemeral=True)
            return
        
        await interaction.response.defer()
        try:
            url = "https://api.wolframalpha.com/v1/result"
            params = {"appid": self.wolfram_key, "i": query}
            
            async with self.session.get(url, params=params, timeout=15) as resp:
                if resp.status == 501:
                    await interaction.followup.send("❌ Couldn't understand that query.")
                    return
                if resp.status != 200:
                    await interaction.followup.send(f"❌ API error: {resp.status}")
                    return
                result = await resp.text()
                embed = discord.Embed(title="🔢 Wolfram Alpha", color=Colors.INFO)
                embed.add_field(name="📝 Query", value=query[:500], inline=False)
                embed.add_field(name="✅ Result", value=result[:1000], inline=False)
                await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {str(e)[:100]}")

    @app_commands.command(name="translate", description="🌐 Translate text")
    @app_commands.describe(text="Text to translate", to_lang="Target language")
    @app_commands.choices(to_lang=[
        app_commands.Choice(name="Spanish", value="es"),
        app_commands.Choice(name="French", value="fr"),
        app_commands.Choice(name="German", value="de"),
        app_commands.Choice(name="Japanese", value="ja"),
        app_commands.Choice(name="Korean", value="ko"),
        app_commands.Choice(name="Chinese", value="zh-CN"),
        app_commands.Choice(name="Arabic", value="ar"),
        app_commands.Choice(name="Russian", value="ru"),
        app_commands.Choice(name="English", value="en")
    ])
    async def translate(self, interaction: discord.Interaction, text: str, to_lang: str):
        """Translate text using MyMemory (free)."""
        await interaction.response.defer()
        try:
            url = "https://api.mymemory.translated.net/get"
            params = {"q": text[:500], "langpair": f"en|{to_lang}"}
            
            async with self.session.get(url, params=params, timeout=15) as resp:
                if resp.status != 200:
                    await interaction.followup.send("❌ Translation failed.")
                    return
                data = await resp.json()
                translated = data.get("responseData", {}).get("translatedText", "")
                if not translated:
                    await interaction.followup.send("❌ Could not translate.")
                    return
                
                langs = {"es": "Spanish", "fr": "French", "de": "German", "ja": "Japanese", 
                         "ko": "Korean", "zh-CN": "Chinese", "ar": "Arabic", "ru": "Russian", "en": "English"}
                embed = discord.Embed(title=f"🌐 → {langs.get(to_lang, to_lang)}", color=Colors.INFO)
                embed.add_field(name="📝 Original", value=text[:500], inline=False)
                embed.add_field(name="✅ Translated", value=translated[:1000], inline=False)
                await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {str(e)[:100]}")

    # ═══════════════════════════════════════════════════════════════════════
    #                            STEAM GROUP  
    # ═══════════════════════════════════════════════════════════════════════

    steam_group = app_commands.Group(name="steam", description="Steam game and player lookups")

    @steam_group.command(name="game", description="🎮 Look up a Steam game")
    @app_commands.describe(name="Game name")
    async def steam_game(self, interaction: discord.Interaction, name: str):
        """Search for a Steam game."""
        await interaction.response.defer()
        try:
            params = {"term": name, "cc": "us", "l": "en"}
            async with self.session.get("https://store.steampowered.com/api/storesearch", params=params, timeout=15) as resp:
                if resp.status != 200:
                    await interaction.followup.send("❌ Steam search failed.")
                    return
                data = await resp.json()
                items = data.get("items", [])
                if not items:
                    await interaction.followup.send(f"❌ No game found for '{name}'")
                    return
                app_id = items[0]["id"]
            
            params = {"appids": app_id, "cc": "us", "l": "en"}
            async with self.session.get("https://store.steampowered.com/api/appdetails", params=params, timeout=15) as resp:
                if resp.status != 200:
                    await interaction.followup.send("❌ Failed to get details.")
                    return
                data = await resp.json()
                game = data.get(str(app_id), {}).get("data", {})
                if not game:
                    await interaction.followup.send("❌ No game data.")
                    return
                
                embed = discord.Embed(
                    title=f"🎮 {game.get('name', 'Unknown')}",
                    description=game.get("short_description", "")[:500],
                    url=f"https://store.steampowered.com/app/{app_id}",
                    color=Colors.INFO
                )
                if game.get("is_free"):
                    embed.add_field(name="💰 Price", value="Free", inline=True)
                elif game.get("price_overview"):
                    price = game["price_overview"].get("final_formatted", "N/A")
                    embed.add_field(name="💰 Price", value=price, inline=True)
                if game.get("developers"):
                    embed.add_field(name="👨‍💻 Dev", value=game["developers"][0], inline=True)
                if game.get("metacritic"):
                    embed.add_field(name="⭐ Meta", value=f"{game['metacritic']['score']}/100", inline=True)
                if game.get("header_image"):
                    embed.set_image(url=game["header_image"])
                await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {str(e)[:100]}")

    @steam_group.command(name="player", description="🎮 Look up a Steam player")
    @app_commands.describe(steam_id="Steam ID or vanity URL")
    async def steam_player(self, interaction: discord.Interaction, steam_id: str):
        """Look up a Steam player profile."""
        if not self.steam_key:
            await interaction.response.send_message("❌ Steam API key not configured.", ephemeral=True)
            return
        
        await interaction.response.defer()
        try:
            # Resolve vanity URL if needed
            if not steam_id.isdigit():
                url = "https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/"
                params = {"key": self.steam_key, "vanityurl": steam_id}
                async with self.session.get(url, params=params, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("response", {}).get("success") == 1:
                            steam_id = data["response"]["steamid"]
                        else:
                            await interaction.followup.send(f"❌ Couldn't resolve '{steam_id}'")
                            return
            
            url = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"
            params = {"key": self.steam_key, "steamids": steam_id}
            async with self.session.get(url, params=params, timeout=15) as resp:
                if resp.status != 200:
                    await interaction.followup.send("❌ Failed to fetch profile.")
                    return
                data = await resp.json()
                players = data.get("response", {}).get("players", [])
                if not players:
                    await interaction.followup.send(f"❌ No player with ID '{steam_id}'")
                    return
                
                p = players[0]
                status = {0: "🔴 Offline", 1: "🟢 Online", 2: "🔴 Busy", 3: "🟡 Away", 4: "💤 Snooze", 5: "🔄 Trading", 6: "🎮 Looking to Play"}
                
                embed = discord.Embed(title=f"🎮 {p.get('personaname', 'Unknown')}", url=p.get("profileurl"), color=Colors.INFO)
                embed.add_field(name="Status", value=status.get(p.get("personastate", 0), "?"), inline=True)
                if p.get("gameextrainfo"):
                    embed.add_field(name="🎯 Playing", value=p["gameextrainfo"], inline=True)
                if p.get("avatarfull"):
                    embed.set_thumbnail(url=p["avatarfull"])
                embed.set_footer(text=f"ID: {steam_id}")
                await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {str(e)[:100]}")


async def setup(bot: commands.Bot):
    await bot.add_cog(APIs(bot))
