from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('myapp', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='elibrarymodel',
            name='dropbox_thumbnail_path',
            field=models.CharField(blank=True, max_length=500, null=True, verbose_name='Dropbox Thumbnail Path'),
        ),
        migrations.AlterField(
            model_name='elibrarymodel',
            name='thumbnail',
            field=models.ImageField(blank=True, null=True, upload_to='elibrary/thumbnails/', verbose_name='Thumbnail Image'),
        ),
        migrations.AlterField(
            model_name='elibrarybody',
            name='image',
            field=models.ImageField(blank=True, null=True, upload_to='hardbooks/images/', verbose_name='Book Image'),
        ),
    ]
