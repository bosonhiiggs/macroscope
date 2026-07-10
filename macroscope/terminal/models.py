from django.db import models


class Terminal(models.Model):
    """Заготовка под мультитерминальность; в реальной Steiza уже существует."""

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=64, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
