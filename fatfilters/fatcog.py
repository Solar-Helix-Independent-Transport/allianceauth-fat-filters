# Cog Stuff
from datetime import timedelta
from discord.ext import commands
from discord.embeds import Embed
from discord.colour import Color
# AA Contexts
from django.conf import settings
from django.contrib.auth.models import User, Group
from django.db.models import Count
from django.utils import timezone
from django.core.exceptions import ObjectDoesNotExist
from allianceauth.eveonline.models import EveCharacter
# AA-Discordbot
from aadiscordbot.cogs.utils.decorators import message_in_channels, sender_has_any_perm, sender_has_perm
from allianceauth.services.modules.discord.models import DiscordUser

from afat.models import AFat
from corptools.models import FullyLoadedFilter
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
            .values("character__character_ownership__user__profile__main_character__character_name") \
            .annotate(Count(f'id'))
        fat_count = fats.count()
        mains = {}
        if fat_count > 0:
            for f in fats:
                mains[f['character__character_ownership__user__profile__main_character__character_name']] = f['id__count']
        embed = Embed()
        embed.title = f"{user.corporation_ticker} FAT Activity"
        gap = "          "
        leaderboard = [f"{t}{gap[len(str(t)):10]}{c}" for c,t in {k: v for k, v in sorted(mains.items(), key=lambda item: item[1], reverse=True)}.items()]
        message = "\n".join(leaderboard)
        embed.description = f'Data from last 3 months.\n```Fats      Main\n{message}```'

        embed.add_field(name="Last 3 Months",
                        value=fat_count, 
                        inline=False)
        await ctx.message.author.send(embed=embed)
        if ctx.guild is not None:
            return await ctx.message.delete()


    @commands.command(pass_context=True, hidden=True)
    @sender_has_any_perm(['corputils.view_alliance_corpstats', 'corpstats.view_alliance_corpstats'])
    @message_in_channels(settings.ADMIN_DISCORD_BOT_CHANNELS)
    async def audit(self, ctx):
        """
        Gets Auth/audit data about a character 
        Input: a Eve Character Name
        """
        input_name = ctx.message.content[7:].strip()

        embed = Embed(
            title="Account Audit {character_name}".format(
                character_name=input_name)
        )

        try:
            char = EveCharacter.objects.get(character_name=input_name)

            try:
                main = char.character_ownership.user.profile.main_character
                state = char.character_ownership.user.profile.state.name
                groups = char.character_ownership.user.groups.all().values_list('name', flat=True)
                alts = char.character_ownership.user.character_ownerships.all().select_related('character').values_list(
                    'character__character_name', 'character__corporation_ticker', 'character__character_id', 'character__corporation_id')
                ghosts = char.character_ownership.user.character_ownerships.all().select_related('character').filter(character__corporation_id=98534707)
                ghost = ""
                if ghosts.exists():
                    _g = []
                    for g in ghosts:
                        _g.append(g.character.character_name)
                    ghost = "**Ghosts:** {}".format(
                        ", ".join(_g)
                    )
                else:
                    ghost = "**No Ghost Found!!!**"
                try:
                    discord_string = "<@{}>".format(
                        char.character_ownership.user.discord.uid)
                except Exception as e:
                    logger.error(e)
                    discord_string = "unknown"

                start_time = timezone.now() - timedelta(days=90)
                character_list = char.character_ownership.user.character_ownerships.all()
                fats = AFat.objects.filter(character__in=character_list.values("character"), afatlink__afattime__gte=start_time) \
                    .order_by("-afatlink__afattime")
                fat_count = fats.count()
                last_message = "**No Fleet Activity!!**"
                if fat_count > 0:
                    ships = set(fats.values_list('shiptype', flat=True))
                    ships = list(ships)[:10]
                    last_fleet = fats.first().afatlink
                    last_date = last_fleet.afattime.strftime("%Y-%m-%d %H:%M")
                    last_message = f"**Last Fleet:** {last_fleet.character}: {last_fleet.fleet} ({last_date})"
                embed.add_field(name="Fats (3 Month)",
                                value=fat_count, 
                                inline=False)
                if fat_count > 0:
                    last_message +=f"\n**Recent Ships:** {', '.join(ships)}"

                embed.description = "**{0}** is linked to **{1} [{2}]** (State: {3})\n{4}\n{5}".format(
                    char,
                    main,
                    main.corporation_ticker,
                    state,
                    last_message,
                    ghost
                )

                alt_list = ["[{}](https://evewho.com/character/{}) *[ [{}](https://evewho.com/corporation/{}) ]*".format(
                    a[0], a[2], a[1], a[3]) for a in alts]
                for idx, names in enumerate([alt_list[i:i + 6] for i in range(0, len(alt_list), 6)]):
                    if idx < 6:
                        embed.add_field(
                            name="Linked Characters {}".format(idx+1), value=", ".join(names), inline=False
                        )
                    else:
                        embed.add_field(
                            name="Linked Characters {} **( Discord Limited There are More )**".format(idx), value=", ".join(names), inline=False
                        )
                        break
                loaded = FullyLoadedFilter(name="fl", description="fl").audit_filter([char.character_ownership.user])
                if not loaded[char.character_ownership.user.id]['check']:
                    embed.add_field(
                        name="Characters Missing From Audit", value=loaded[char.character_ownership.user.id]["message"], inline=False
                    )

                if len(groups) > 0:
                    embed.add_field(
                        name="Groups", value=", ".join(groups), inline=False
                    )

                embed.add_field(
                    name="Discord Link", value=discord_string, inline=False
                )

                return await ctx.send(embed=embed)
            except ObjectDoesNotExist:
                users = char.ownership_records.values('user')
                users = User.objects.filter(id__in=users)
                characters = EveCharacter.objects.filter(
                    ownership_records__user__in=users).distinct()
                embed = Embed(title="Character Lookup")
                embed.colour = Color.blue()
                embed.description = "**{0}** is Unlinked searching for any characters linked to known users".format(
                    char,
                )
                user_names = ["{}".format(user.username) for user in users]
                if len(user_names) == 0:
                    user_names = "No User Links found"
                else:
                    user_names = ", ".join(user_names)

                embed.add_field(
                    name="Old Users", value=user_names, inline=False
                )

                alt_list = ["[{}](https://evewho.com/character/{}) *[ [{}](https://evewho.com/corporation/{}) ]*".format(a.character_name,
                                                                                                                         a.character_id,
                                                                                                                         a.corporation_ticker,
                                                                                                                         a.corporation_id
                                                                                                                         ) for a in characters]
                for idx, names in enumerate([alt_list[i:i + 6] for i in range(0, len(alt_list), 6)]):
                    if idx < 6:
                        embed.add_field(
                            name="Found Characters {}".format(idx+1), value=", ".join(names), inline=False
                        )
                    else:
                        embed.add_field(
                            name="Found Characters {} **( Discord Limited There are More )**".format(idx), value=", ".join(names), inline=False
                        )
                        break

                return await ctx.send(embed=embed)

        except EveCharacter.DoesNotExist:
            embed.colour = Color.red()

            embed.description = (
                "Character **{character_name}** does not exist in our Auth system"
            ).format(character_name=input_name)

            return await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Fats(bot))
