# Generated by Django 3.2.8 on 2021-12-21 11:22

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('corptools', '0059_invtypematerials_met_type'),
        ('fatfilters', '0002_fatintimeperiod_ship_names'),
    ]

    operations = [
        migrations.AlterField(
            model_name='fatintimeperiod',
            name='ship_names',
            field=models.ManyToManyField(blank=True, limit_choices_to={'group__category_id': 6}, to='corptools.EveItemType'),
        ),
    ]
