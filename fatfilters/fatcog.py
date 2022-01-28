# Cog Stuff
from datetime import timedelta
from discord.ext import commands
from discord.embeds import Embed
from discord.colour import Color
# AA Contexts
from django.conf import settings
from django.contrib.auth.models import User, Group
from django.utils import timezone
from django.core.exceptions import ObjectDoesNotExist
from allianceauth.eveonline.models import EveCharacter
# AA-Discordbot
from aadiscordbot.cogs.utils.decorators import sender_has_perm
from allianceauth.services.modules.discord.models import DiscordUser

from afat.models import AFat

import re

import logging

logger = logging.getLogger(__name__)


class Fats(commands.Cog):
    """
    All about fats!
    """
    def __init__(self, bot):
        self.bot = bot

    @commands.command(pass_context=True)
    async def me(self, ctx):
        """
        Show your users basic stats from the FAT module
        """
        start_time = timezone.now() - timedelta(days=90)
        user = DiscordUser.objects.get(uid=ctx.message.author.id).user
        character_list = user.character_ownerships.all()
        fats = AFat.objects.filter(character__in=character_list.values("character"), afatlink__afattime__gte=start_time) \
            .order_by("-afatlink__afattime")
        fat_count = fats.count()
        if fat_count > 0:
            ships = set(fats.values_list('shiptype', flat=True))
            ships = list(ships)[:10]
            last_fleet = fats.first().afatlink
            last_date = last_fleet.afattime.strftime("%Y-%m-%d %H:%M")
            last_message = f"{last_fleet.character}: {last_fleet.fleet} ({last_date})"
        embed = Embed()
        embed.title = "Recent FAT Activity"
        embed.description = f"Plese check auth for more info!"

        embed.add_field(name="Last 3 Months",
                        value=fat_count, 
                        inline=False)
        if fat_count > 0:
            embed.add_field(name="Recent Ships",
                            value=", ".join(ships), 
                            inline=False)
            embed.add_field(name="Last Fleet",
                            value=last_message, 
                            inline=False)
        await ctx.message.author.send(embed=embed)
        if ctx.guild is not None:
            return await ctx.message.delete()

    @commands.command(pass_context=True)
    @sender_has_perm("afat.stats_corporation_own")
    async def corp(self, ctx):
        """
        Show your corps basic stats from the FAT module
        """

        start_time = timezone.now() - timedelta(days=90)
        user = DiscordUser.objects.get(uid=ctx.message.author.id).user.profile.main_character

        character_list = EveCharacter.objects.filter(character_ownership__user__profile__main_character__corporation_id=user.corporation_id)

        fats = AFat.objects.filter(character__in=character_list, afatlink__afattime__gte=start_time) \
            .order_by("-afatlink__afattime")
        fat_count = fats.count()
        mains = {}
        if fat_count > 0:
            last_fleet = fats.first().afatlink
            last_date = last_fleet.afattime.strftime("%Y-%m-%d %H:%M")
            for f in fats:
                if f.character.character_ownership.user.profile.main_character.character_name not in mains:
                    mains[f.character.character_ownership.user.profile.main_character.character_name] = 0
                mains[f.character.character_ownership.user.profile.main_character.character_name] += 1
        embed = Embed()
        embed.title = "Recent FAT Activity"
        gap = "          "
        leaderboard = [f"{t}{gap[len(str(t)):10]}{c}" for c,t in {k: v for k, v in sorted(mains.items(), key=lambda item: item[1])}.items()]
        leaderboard.sort()
        message = "\n".join(leaderboard)
        embed.description = f'```Fats      Main\n{message}```'

        embed.add_field(name="Last 3 Months",
                        value=fat_count, 
                        inline=False)
        await ctx.message.author.send(embed=embed)
        if ctx.guild is not None:
            return await ctx.message.delete()

def setup(bot):
    bot.add_cog(Fats(bot))
