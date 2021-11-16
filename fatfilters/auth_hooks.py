from allianceauth.services.hooks import UrlHook
from allianceauth import hooks
"""from . import urls

@hooks.register('url_hook')
def register_url():
    return UrlHook(urls, 'srpmod', r'^srpmod/')
"""

from .models import FATInTimePeriod

@hooks.register('secure_group_filters') # this is the critical name we are searching for.
def filters(): # can be any name
    return [FATInTimePeriod] # pass in the model classes as an array.
