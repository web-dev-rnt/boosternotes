from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('myapp', '0024_elibrarypdf_is_demo'),
    ]

    operations = [
        migrations.AddField(
            model_name='elibrarypdf',
            name='display_order',
            field=models.PositiveIntegerField(default=0, verbose_name='Display Order'),
        ),
        migrations.AlterModelOptions(
            name='elibrarypdf',
            options={
                'ordering': ['display_order', 'uploaded_at'],
                'verbose_name': 'E-Library PDF',
                'verbose_name_plural': 'E-Library PDFs',
            },
        ),
    ]
