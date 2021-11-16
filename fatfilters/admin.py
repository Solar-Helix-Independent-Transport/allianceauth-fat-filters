from django.contrib import admin
from .models import FATInTimePeriod
# Register your models here.

@admin.register(FATInTimePeriod)
class FATAdmin(admin.ModelAdmin):
    list_display = ("name", "description", "days", "fats_needed")
    filter_horizontal = ('ship_names',)

    select_related=True


