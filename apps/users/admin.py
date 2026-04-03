from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    # Fields to display in the user list
    list_display = ('email', 'full_name', 'is_staff', 'is_active', 'date_joined')
    
    # Filters on the right sidebar
    list_filter = ('is_staff', 'is_active')
    
    # Searchable fields in the admin
    search_fields = ('email', 'full_name')
    
    # Default ordering
    ordering = ('email',)
    
    # Fields layout in the edit page
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ('full_name',)}),
        ('Permissions', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')
        }),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    
    # Fields layout when creating a new user via admin
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'full_name', 'password1', 'password2', 'is_active', 'is_staff'),
        }),
    )
