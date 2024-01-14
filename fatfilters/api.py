from __future__ import annotations
from datetime import timedelta
from tokenize import group
from typing import List
from unicodedata import category
from allianceauth import notifications
from corptools import app_settings
from django.utils.timezone import activate
from fatfilters import schema

from ninja import NinjaAPI, Form, main
from ninja.security import django_auth
from ninja.responses import codes_4xx

from django.core.exceptions import PermissionDenied
from django.db.models import F, Sum, Q, Count
from allianceauth.eveonline.models import EveCharacter
from django.conf import settings
from django.utils import timezone

from afat.models import Fat

from . import models

import logging


from django.utils.cache import get_cache_key, learn_cache_key, patch_response_headers


logger = logging.getLogger(__name__)


api = NinjaAPI(title="CorpTools API", version="0.0.1",
               urls_namespace='fats:api', auth=django_auth, csrf=True,
               openapi_url=settings.DEBUG and "/openapi.json" or "")

def get_visible_fat_qs(user):
    start_time = timezone.now() - timedelta(days=90)
    fats = Fat.objects.select_related("character", "character__character_ownership__user__profile__main_character").filter(afatlink__afattime__gte=start_time)

    if user.has_perm("afat.stats_corporation_other") or user.has_perm("afat.manage_afat"):
        return fats

    if user.has_perm("afat.stats_corporation_own"):
        return fats.filter(character__character_ownership__user__profile__main_character__corporations_id=user.profile.main_character.corporation_id)
    
    return Fat.objects.none()
    
@api.get(
    "fat/{character_id}",
    response={200: List[schema.Fat], 403: schema.Message},
    tags=["Fat"]
)
def get_character_fats(request, character_id: int):
    start_time = timezone.now() - timedelta(days=90)
    char = EveCharacter.objects.get(character_id=character_id)
    user = char.character_ownership.user
    character_list = user.character_ownerships.all()
    fats = AFat.objects.filter(character__in=character_list.values("character")) \
        .order_by("-afatlink__afattime").select_related("character", "afatlink")

    output = []
    for f in fats:
        output.append(
            {
                "character": f.character,
                "fleet_name": f.afatlink.fleet,
                "time": f.afatlink.afattime,
                "ship": f.shiptype,
                "system": f.system
            }
        )
    return output
    
@api.get(
    "fat/visible",
    response={200: List, 403: schema.Message},
    tags=["Fat"]
)
def get_visible_fats(request):
    fats = get_visible_fat_qs(request.user)
    