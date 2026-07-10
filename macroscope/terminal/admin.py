from django.contrib import admin

from terminal.models import Terminal


@admin.register(Terminal)
class TerminalAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'slug', 'is_active')
    search_fields = ('name', 'slug')
