# Cog Stuff
from datetime import timedelta
from aadiscordbot.utils.auth import get_auth_user
from discord import AutocompleteContext, option
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
from aadiscordbot.cogs.utils.decorators import has_any_perm, in_channels, message_in_channels, sender_has_any_perm, sender_has_perm
from allianceauth.services.modules.discord.models import DiscordUser
from aadiscordbot.app_settings import get_site_url, get_all_servers
from aadiscordbot.cogs.utils.autocompletes import search_characters

from afat.models import Fat
from corptools.models import FullyLoadedFilter
import re
from discord.utils import get
from .models import FATCogConfiguration
import logging

logger = logging.getLogger(__name__)


class Fats(commands.Cog):
    """
    All about fats!
    """
    def __init__(self, bot):
        self.bot = bot


    @commands.slash_command(name='me', guild_ids=get_all_servers())
    @option("months", description="Number of months to look back!", min_value=1, max_value=12, default=3)
    async def me(self, ctx, months: int):
        """
        Show your users basic stats from the FAT module
        """
        try:
            await ctx.defer(ephemeral=True)
            start_time = timezone.now() - timedelta(days=months*30)
            user = get_auth_user(ctx.author, ctx.guild)
            character_list = user.character_ownerships.all()

            fat_config = FATCogConfiguration.get_solo()
            fat_types = fat_config.fleet_type_filter.all()
            fats = Fat.objects.filter(
                character__in=character_list.values("character"),
                fatlink__created__gte=start_time,
                fatlink__fleet_type__in=fat_types.values_list('name', flat=True),
                fatlink__fleet_type__isnull=False
            ).order_by("-fatlink__created")
            fat_count = fats.count()
            if fat_count > 0:
                ships = set(fats.values_list('shiptype', flat=True))
                ships = list(ships)[:10]
                last_fleet = fats.first().fatlink
                last_date = last_fleet.created.strftime("%Y-%m-%d %H:%M")
                last_message = f"{last_fleet.character}: {last_fleet.fleet} ({last_date})"
            embed = Embed()
            embed.title = "Recent FAT Activity"
            embed.description = f"Plese check auth for more info!"

            embed.add_field(name=f"Last {months} Months",
                            value=fat_count, 
                            inline=False)
            if fat_count > 0:
                embed.add_field(name="Recent Ships",
                                value=", ".join(ships), 
                                inline=False)
                embed.add_field(name="Last Fleet",
                                value=last_message, 
                                inline=False)
            await ctx.respond(embed=embed, ephemeral=True)
        except commands.MissingPermissions as e:
            return await ctx.respond(e.missing_permissions[0], ephemeral=True)


    @commands.slash_command(name='corp', guild_ids=get_all_servers())
    @option("months", description="Number of months to look back!", min_value=1, max_value=12, default=3)
    @option("current_only", description="This month only!", default=False)
    async def corp(self, ctx, months: int, current_only: bool=False):
        """
        Show your corps basic stats from the FAT module
        """
        try:
            has_any_perm(
                ctx.author.id, 
                ['afat.stats_corporation_own'],
                guild=ctx.guild
            )
            await ctx.defer(ephemeral=True)
            start_time = timezone.now() 
            if current_only:
                start_time = start_time.replace(day=1, hour=0)
            else: 
                start_time = start_time - timedelta(days=months*30)
            user = user = get_auth_user(ctx.author, ctx.guild)
            user = user.profile.main_character

            character_list = EveCharacter.objects.filter(
                character_ownership__user__profile__main_character__corporation_id=user.corporation_id)
            fat_config = FATCogConfiguration.get_solo()
            fat_types = fat_config.fleet_type_filter.all()

            fats = Fat.objects.filter(
                character__in=character_list,
                fatlink__created__gte=start_time,
                fatlink__fleet_type__in=fat_types.values_list('name', flat=True),
                fatlink__fleet_type__isnull=False
            ).values(
                "character__character_ownership__user__profile__main_character__character_name"
            ).annotate(Count(f'id'))

            fats_non_strat = Fat.objects.filter(
                character__in=character_list,
                fatlink__created__gte=start_time,
            ).values(
                "character__character_ownership__user__profile__main_character__character_name"
            ).exclude(
                fatlink__link_type__in=fat_types
            ).annotate(Count(f'id'))

            non_strat = {}
            for f in fats_non_strat:
                non_strat[f['character__character_ownership__user__profile__main_character__character_name']] = f['id__count']

            fat_count = fats_non_strat.count()
            mains = {}
            if fat_count > 0:
                for f in fats:
                    mains[f['character__character_ownership__user__profile__main_character__character_name']] = f['id__count']
            embed = Embed()
            embed.title = f"{user.corporation_ticker} FAT Activity"
            gap = "               "
            leaderboard = []
            for c,t in {
                    k: v for k, v in sorted(
                        mains.items(),
                        key=lambda item: item[1],
                        reverse=True
                    )
                }.items():
                str_fat = f"{t}(+{non_strat.get(c,0)})"
                gap_pad = len(str(str_fat))
                leaderboard.append(f"{str_fat}{gap[gap_pad:15]}{c}")
            message = "\n".join(leaderboard)
            embed.description = f'Data since {start_time.strftime("%Y/%m/%d")}\n```Fats           Main\n{message}```\nStrat Fats(+ Non Strat Fats)'

            embed.add_field(name=f"Mains seen in last {months} Months",
                            value=fat_count,
                            inline=False)
            await ctx.respond(embed=embed, ephemeral=True)
        except commands.MissingPermissions as e:
            return await ctx.respond(e.missing_permissions[0], ephemeral=True)

    async def audit_embed(self, input_name):
        embed = Embed(
            title="Account Audit {character_name}".format(
                character_name=input_name)
        )

        try:
            char = EveCharacter.objects.get(character_name=input_name)

            try:
                main = char.character_ownership.user.profile.main_character
                state = char.character_ownership.user.profile.state.name
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

                    user = get(self.bot.get_all_members(), id=char.character_ownership.user.discord.uid)
                    try:
                        if user:
                        #url = user.avatar.url
                            is_bot = user.bot
                            created_at = user.created_at
                            desktop_status = user.desktop_status.name
                            mobile_status = user.mobile_status.name
                            web_status = user.web_status.name
                            status = user.status.name
                            name = f"**{user.display_name}** `{user.name}@{user.discriminator}` <@{user.id}>"
                            stat_str = f"**Status:** {status} (D: {desktop_status}, M: {mobile_status}, W: {web_status}) B:{is_bot}"
                            date_time = created_at.strftime("%Y/%m/%d %H:%M:%S")
                            discord_string = f"{name}\n{stat_str}\n**User Created:** {date_time}"
                    except Exception as e:
                        logger.error(e)
                except Exception as e:
                    logger.error(e)
                    discord_string = "unknown"

                start_time = timezone.now() - timedelta(days=90)
                character_list = char.character_ownership.user.character_ownerships.all()
                fats = Fat.objects.filter(character__in=character_list.values("character"), fatlink__created__gte=start_time) \
                    .order_by("-fatlink__created")
                fat_count = fats.count()
                last_message = "**No Fleet Activity!!**"
                if fat_count > 0:
                    ships = set(fats.values_list('shiptype', flat=True))
                    ships = list(ships)[:10]
                    last_fleet = fats.first().fatlink
                    last_date = last_fleet.created.strftime("%Y-%m-%d %H:%M")
                    last_message = f"**Last Fleet:** {last_fleet.character}: {last_fleet.fleet} ({last_date})"
                embed.add_field(name="Fats (3 Month)",
                                value=fat_count, 
                                inline=False)
                if fat_count > 0:
                    last_message +=f"\n**Recent Ships:** {', '.join(ships)}"
                url = "[Auth Audit Link]({})".format(get_site_url() + "/audit/r/" + str(main.character_id) + "/")
                embed.description = "**{0}** is linked to **{1} [{2}]** (State: {3})\n{4}\n{5}\n{6}".format(
                    char,
                    main,
                    main.corporation_ticker,
                    state,
                    last_message,
                    ghost,
                    url
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

                # if len(groups) > 0:
                #     embed.add_field(
                #         name="Groups", value=", ".join(groups), inline=False
                #     )

                embed.add_field(
                    name="Discord Link", value=discord_string, inline=False
                )

                return embed
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

                return embed

        except EveCharacter.DoesNotExist:
            embed.colour = Color.red()

            embed.description = (
                "Character **{character_name}** does not exist in our Auth system"
            ).format(character_name=input_name)

            return embed


    @commands.command(pass_context=True, hidden=True)
    @sender_has_any_perm(
        [
            'corputils.view_alliance_corpstats',
            'corpstats.view_alliance_corpstats',
            'aadiscordbot.member_command_access'
        ]
    )
    @message_in_channels(settings.ADMIN_DISCORD_BOT_CHANNELS)
    async def audit(self, ctx):
        """
        Gets Auth/audit data about a character 
        Input: a Eve Character Name
        """
        return await ctx.send(embed=await self.audit_embed(ctx.message.content[7:].strip()))


    @commands.slash_command(name='audit', guild_ids=get_all_servers())
    @option("character", description="Search for a Character!", autocomplete=search_characters)
    async def slash_audit(
        self,
        ctx,
        character: str,
    ):
        try:
            in_channels(ctx.channel.id, settings.ADMIN_DISCORD_BOT_CHANNELS)
            has_any_perm(
                ctx.author.id, 
                [
                    'corputils.view_alliance_corpstats',
                    'corpstats.view_alliance_corpstats',
                    'aadiscordbot.member_command_access'
                ]
            )
            await ctx.defer()
            return await ctx.respond(embed=await self.audit_embed(character))
        except commands.MissingPermissions as e:
            return await ctx.respond(e.missing_permissions[0], ephemeral=True)


                    

def setup(bot):
    bot.add_cog(Fats(bot))
