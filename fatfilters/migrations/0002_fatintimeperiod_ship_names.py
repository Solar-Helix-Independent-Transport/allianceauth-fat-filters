# Generated by Django 3.2.8 on 2021-11-16 09:11

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('corptools', '0059_invtypematerials_met_type'),
        ('fatfilters', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='fatintimeperiod',
            name='ship_names',
            field=models.ManyToManyField(blank=True, to='corptools.EveItemType'),
        ),
    ]
