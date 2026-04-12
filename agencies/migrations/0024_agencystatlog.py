from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('agencies', '0023_basexplog'),
    ]

    operations = [
        migrations.CreateModel(
            name='AgencyStatLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('stat_type', models.CharField(choices=[('attribute', 'Attribute'), ('integrity', 'Integrity')], max_length=20)),
                ('stat_path', models.CharField(help_text="e.g. 'power.Science' for attributes, 'integrity' for integrity.", max_length=100)),
                ('amount', models.IntegerField(help_text='Change amount (positive or negative).')),
                ('reason', models.CharField(max_length=500)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('agency', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='stat_logs', to='agencies.agency')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
