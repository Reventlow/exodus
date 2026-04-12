from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('agencies', '0022_add_condition_types'),
    ]

    operations = [
        migrations.CreateModel(
            name='BaseXpLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.IntegerField(help_text='XP amount (negative = cost/loss).')),
                ('reason', models.CharField(max_length=300)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('agency', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='base_xp_logs', to='agencies.agency')),
                ('base', models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, related_name='xp_logs', to='agencies.base')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
