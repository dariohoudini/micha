from django.contrib import admin
from .models import Case, CaseSubject, CaseLink, CaseEvent


@admin.register(Case)
class CaseAdmin(admin.ModelAdmin):
    list_display = ('code', 'title', 'kind', 'status', 'priority',
                    'assigned_to', 'sla_at', 'created_at')
    list_filter = ('kind', 'status', 'priority')
    search_fields = ('code', 'title', 'subject_id', 'summary')
    readonly_fields = ('code', 'created_at', 'updated_at', 'resolved_at')


@admin.register(CaseSubject)
class CaseSubjectAdmin(admin.ModelAdmin):
    list_display = ('case', 'user', 'role', 'added_at')
    list_filter = ('role',)
    search_fields = ('user__email', 'case__code')


@admin.register(CaseLink)
class CaseLinkAdmin(admin.ModelAdmin):
    list_display = ('case', 'link_type', 'ref_type', 'ref_id', 'added_at')
    list_filter = ('link_type', 'ref_type')
    search_fields = ('ref_id',)


@admin.register(CaseEvent)
class CaseEventAdmin(admin.ModelAdmin):
    list_display = ('id', 'case', 'event_type', 'actor', 'actor_role', 'created_at')
    list_filter = ('event_type', 'actor_role')
    readonly_fields = tuple(f.name for f in CaseEvent._meta.fields)
