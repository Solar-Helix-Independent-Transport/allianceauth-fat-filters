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

    # --- Helpers ---

    async def _resolve_auth_user(self, ctx):
        try:
            return get_auth_user(ctx.author, ctx.guild)
        except Exception:
            await ctx.respond("Your Discord account is not linked to Auth.", ephemeral=True)
            return None

    async def _get_fat_type_names(self, ctx):
        fat_types = FATCogConfiguration.get_solo().fleet_type_filter.all()
        if not fat_types.exists():
            await ctx.respond("No fleet types are configured.", ephemeral=True)
            return None
        return fat_types.values_list('name', flat=True)

    def _add_character_fields(self, embed, char_list, label):
        for idx, chunk in enumerate([char_list[i:i+6] for i in range(0, len(char_list), 6)]):
            if idx < 6:
                embed.add_field(name=f"{label} {idx+1}", value=", ".join(chunk), inline=False)
            else:
                embed.add_field(name=f"{label} {idx} **(Discord Limited There are More)**", value=", ".join(chunk), inline=False)
                break

    def _discord_info_string(self, auth_user):
        try:
            discord_uid = auth_user.discord.uid
            discord_string = f"<@{discord_uid}>"
            member = get(self.bot.get_all_members(), id=discord_uid)
            if not member:
                return discord_string
            try:
                username = f"{member.name}#{member.discriminator}" if member.discriminator != "0" else member.name
                name = f"**{member.display_name}** `{username}` <@{member.id}>"
                stat_str = (
                    f"**Status:** {member.status.name} "
                    f"(D: {member.desktop_status.name}, M: {member.mobile_status.name}, W: {member.web_status.name}) "
                    f"B:{member.bot}"
                )
                date_time = member.created_at.strftime("%Y/%m/%d %H:%M:%S")
                return f"{name}\n{stat_str}\n**User Created:** {date_time}"
            except Exception as e:
                logger.error(e)
                return discord_string
        except Exception as e:
            logger.error(e)
            return "unknown"

    def _fat_summary(self, auth_user):
        start_time = timezone.now() - timedelta(days=90)
        character_list = auth_user.character_ownerships.all()
        fats = Fat.objects.filter(
            character__in=character_list.values("character"),
            fatlink__created__gte=start_time
        ).order_by("-fatlink__created")
        fat_count = fats.count()
        if fat_count == 0:
            return fat_count, "**No Fleet Activity!!**"
        ships = list(set(fats.values_list('ship__name', flat=True)))[:10]
        last_fleet = fats.first().fatlink
        last_date = last_fleet.created.strftime("%Y-%m-%d %H:%M")
        last_message = (
            f"**Last Fleet:** {last_fleet.character}: {last_fleet.fleet} ({last_date})"
            f"\n**Recent Ships:** {', '.join(ships)}"
        )
        return fat_count, last_message

    # --- Audit embed helpers ---

    def _embed_linked_character(self, char):
        auth_user = char.character_ownership.user
        main = auth_user.profile.main_character
        state = auth_user.profile.state.name

        fat_count, fat_message = self._fat_summary(auth_user)
        discord_string = self._discord_info_string(auth_user)

        ghosts = auth_user.character_ownerships.all().select_related('character').filter(
            character__corporation_id=98534707
        )
        if ghosts.exists():
            ghost = "**Ghosts:** {}".format(", ".join(g.character.character_name for g in ghosts))
        else:
            ghost = "**No Ghost Found!!!**"

        url = "[Auth Audit Link]({})".format(get_site_url() + "/audit/r/" + str(main.character_id) + "/")

        embed = Embed(title=f"Account Audit {char}")
        embed.description = "**{0}** is linked to **{1} [{2}]** (State: {3})\n{4}\n{5}\n{6}".format(
            char, main, main.corporation_ticker, state, fat_message, ghost, url
        )
        embed.add_field(name="Fats (3 Month)", value=fat_count, inline=False)

        alts = auth_user.character_ownerships.all().select_related('character').values_list(
            'character__character_name', 'character__corporation_ticker',
            'character__character_id', 'character__corporation_id'
        )
        alt_list = [
            "[{}](https://evewho.com/character/{}) *[ [{}](https://evewho.com/corporation/{}) ]*".format(
                a[0], a[2], a[1], a[3]
            ) for a in alts
        ]
        self._add_character_fields(embed, alt_list, "Linked Characters")

        loaded = FullyLoadedFilter(name="fl", description="fl").audit_filter([auth_user])
        if not loaded[auth_user.id]['check']:
            embed.add_field(
                name="Characters Missing From Audit",
                value=loaded[auth_user.id]["message"],
                inline=False
            )

        embed.add_field(name="Discord Link", value=discord_string, inline=False)
        return embed

    def _embed_unlinked_character(self, char):
        users = User.objects.filter(id__in=char.ownership_records.values('user'))
        characters = EveCharacter.objects.filter(ownership_records__user__in=users).distinct()

        embed = Embed(title="Character Lookup")
        embed.colour = Color.blue()
        embed.description = "**{0}** is Unlinked searching for any characters linked to known users".format(char)

        user_names = ", ".join(u.username for u in users) or "No User Links found"
        embed.add_field(name="Old Users", value=user_names, inline=False)

        alt_list = [
            "[{}](https://evewho.com/character/{}) *[ [{}](https://evewho.com/corporation/{}) ]*".format(
                c.character_name, c.character_id, c.corporation_ticker, c.corporation_id
            ) for c in characters
        ]
        self._add_character_fields(embed, alt_list, "Found Characters")
        return embed

    def _embed_unknown_character(self, input_name):
        embed = Embed(title=f"Account Audit {input_name}")
        embed.colour = Color.red()
        embed.description = f"Character **{input_name}** does not exist in our Auth system"
        return embed

    async def audit_embed(self, input_name):
        try:
            char = EveCharacter.objects.get(character_name=input_name)
            try:
                return self._embed_linked_character(char)
            except ObjectDoesNotExist:
                return self._embed_unlinked_character(char)
        except EveCharacter.DoesNotExist:
            return self._embed_unknown_character(input_name)

    # --- Commands ---

    @commands.slash_command(name='me', guild_ids=get_all_servers())
    @option("months", description="Number of months to look back!", min_value=1, max_value=12, default=3)
    async def me(self, ctx, months: int):
        """
        Show your users basic stats from the FAT module
        """
        try:
            await ctx.defer(ephemeral=True)
            user = await self._resolve_auth_user(ctx)
            if user is None:
                return
            fat_type_names = await self._get_fat_type_names(ctx)
            if fat_type_names is None:
                return

            start_time = timezone.now() - timedelta(days=months*30)
            fats = Fat.objects.filter(
                character__in=user.character_ownerships.values("character"),
                fatlink__created__gte=start_time,
                fatlink__fleet_type__in=fat_type_names,
            ).order_by("-fatlink__created")
            fat_count = fats.count()
            if fat_count > 0:
                ships = list(set(fats.values_list('shiptype', flat=True)))[:10]
                last_fleet = fats.first().fatlink
                last_date = last_fleet.created.strftime("%Y-%m-%d %H:%M")
                last_message = f"{last_fleet.character}: {last_fleet.fleet} ({last_date})"

            embed = Embed()
            embed.title = "Recent FAT Activity"
            embed.description = "Plese check auth for more info!"
            embed.add_field(name=f"Last {months} Months", value=fat_count, inline=False)
            if fat_count > 0:
                embed.add_field(name="Recent Ships", value=", ".join(ships), inline=False)
                embed.add_field(name="Last Fleet", value=last_message, inline=False)
            await ctx.respond(embed=embed, ephemeral=True)
        except commands.MissingPermissions as e:
            return await ctx.respond(e.missing_permissions[0], ephemeral=True)

    @commands.slash_command(name='corp', guild_ids=get_all_servers())
    @option("months", description="Number of months to look back!", min_value=1, max_value=12, default=3)
    @option("current_only", description="This month only!", default=False)
    async def corp(self, ctx, months: int, current_only: bool = False):
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
            auth_user = await self._resolve_auth_user(ctx)
            if auth_user is None:
                return
            fat_type_names = await self._get_fat_type_names(ctx)
            if fat_type_names is None:
                return

            start_time = timezone.now()
            if current_only:
                start_time = start_time.replace(day=1, hour=0)
            else:
                start_time = start_time - timedelta(days=months*30)

            user = auth_user.profile.main_character
            main_name_field = "character__character_ownership__user__profile__main_character__character_name"
            character_list = EveCharacter.objects.filter(
                character_ownership__user__profile__main_character__corporation_id=user.corporation_id
            )

            fats = Fat.objects.filter(
                character__in=character_list,
                fatlink__created__gte=start_time,
                fatlink__fleet_type__in=fat_type_names,
            ).values(main_name_field).annotate(Count('id'))

            fats_non_strat = Fat.objects.filter(
                character__in=character_list,
                fatlink__created__gte=start_time,
            ).exclude(
                fatlink__fleet_type__in=fat_type_names
            ).values(main_name_field).annotate(Count('id'))

            non_strat = {f[main_name_field]: f['id__count'] for f in fats_non_strat}
            mains = {f[main_name_field]: f['id__count'] for f in fats}
            fat_count = len(mains)

            leaderboard = []
            for c, t in sorted(mains.items(), key=lambda item: item[1], reverse=True):
                str_fat = f"{t}(+{non_strat.get(c, 0)})"
                leaderboard.append(f"{str_fat:<15}{c}")
            message = "\n".join(leaderboard)

            embed = Embed()
            embed.title = f"{user.corporation_ticker} FAT Activity"
            embed.description = (
                f'Data since {start_time.strftime("%Y/%m/%d")}\n'
                f'```Fats           Main\n{message}```\n'
                f'Strat Fats(+ Non Strat Fats)'
            )
            embed.add_field(name=f"Mains seen in last {months} Months", value=fat_count, inline=False)
            await ctx.respond(embed=embed, ephemeral=True)
        except commands.MissingPermissions as e:
            return await ctx.respond(e.missing_permissions[0], ephemeral=True)

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
