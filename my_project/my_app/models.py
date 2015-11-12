from django.db import models

class MyModel(models.Model):
	name = models.CharField('my_name', max_length=255)