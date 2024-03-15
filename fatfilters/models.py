from datetime import timedelta
from collections import defaultdict
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from afat.models import Fat, FleetType
from allianceauth.authentication.models import CharacterOwnership
from corptools.models import EveItemType
from solo.models import SingletonModel

class BaseFilter(models.Model):
    name = models.CharField(max_length=500) # This is the filters name shown to the admin
    description = models.CharField(max_length=500) # this is what is shown to the user

    class Meta:
        abstract = True

    def __str__(self):
        return f"{self.name}: {self.description}"

    def process_filter(self, user: User): #Single User Pass Fail system 
        raise NotImplementedError("Please Create a filter!")

    def audit_filter(self, users): # Bulk check system that also advises the user with simple messages
        raise NotImplementedError("Please Create an audit function!")


class FATInTimePeriod(BaseFilter):
    days = models.IntegerField(default=30)
    fats_needed = models.IntegerField(default=10)

    fleet_type_filter = models.ManyToManyField(FleetType, blank=True)

    ship_names = models.ManyToManyField(EveItemType, blank=True, limit_choices_to={'group__category_id': 6})

    def process_filter(self, user: User): # legacy pass fail
        try:
            start_time = timezone.now() - timedelta(days=self.days)
            character_list = user.character_ownerships.all().select_related('character')
            fat_count = Fat.objects.filter(character__character_id__in=character_list, fatlink__created__gte=start_time)
            ship_names = self.ship_names.all()
            fleet_types = self.ship_names.all()
            
            if ship_names.count() > 0:
                fat_count = fat_count.filter(ship_names__in=ship_names.values_list('name', flat=True))

            if fleet_types.count() > 0:
                fat_count = fat_count.filter(fatlink__link_type__in=fleet_types)

            if fat_count.count() > self.fats_needed:
                return True
            else:
                return False
        except Exception as e:
            return False


    def audit_filter(self, users): # bulk pass fail
        character_list = CharacterOwnership.objects.filter(user__in=users)
        start_time = timezone.now() - timedelta(days=self.days)
        ship_names = self.ship_names.all()
        fleet_types = self.fleet_type_filter.all()

        fats = Fat.objects.filter(character__in=character_list.values("character"), fatlink__created__gte=start_time) \
                .select_related('character__character_ownership__user', 'character')

        if ship_names.count() > 0:
            fats = fats.filter(shiptype__in=ship_names.values_list('name', flat=True))

        if fleet_types.count() > 0:
            fats = fats.filter(fatlink__link_type__in=fleet_types)

        users = defaultdict(list)
        for f in fats:
            users[f.character.character_ownership.user.pk].append(f.id)

        output = defaultdict(lambda: {"message": 0, "check": False})
        for u, fat_list in users.items():
            pass_fail = False
            if len(fat_list) > self.fats_needed:
                pass_fail = True
            output[u] = {"message": len(fat_list), "check": pass_fail}
        return output


class FATCogConfiguration(SingletonModel):
    fleet_type_filter = models.ManyToManyField(FleetType, blank=True)

