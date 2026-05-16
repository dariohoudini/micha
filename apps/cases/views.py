"""
apps/cases/views.py — admin REST surface for cases.
"""
from rest_framework import permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Q

from .models import (
    Case, CaseLink, CaseSubject, CaseEvent,
    CaseStatus, CasePriority, CaseKind, CaseResolution,
)
from . import service


def _serialize_case(c: Case, *, deep: bool = False) -> dict:
    out = {
        'id': c.id, 'code': c.code, 'title': c.title,
        'kind': c.kind, 'status': c.status, 'priority': c.priority,
        'subject_type': c.subject_type, 'subject_id': c.subject_id,
        'assigned_to_id': c.assigned_to_id,
        'assigned_to_email': c.assigned_to.email if c.assigned_to_id else None,
        'opened_by_user_id': c.opened_by_user_id,
        'opened_by_admin_id': c.opened_by_admin_id,
        'summary': c.summary,
        'resolution': c.resolution,
        'resolution_note': c.resolution_note,
        'sla_at': c.sla_at,
        'created_at': c.created_at,
        'updated_at': c.updated_at,
        'resolved_at': c.resolved_at,
    }
    if deep:
        out['links'] = [{
            'id': l.id, 'link_type': l.link_type,
            'ref_type': l.ref_type, 'ref_id': l.ref_id,
            'note': l.note, 'added_at': l.added_at,
        } for l in c.links.all()]
        out['subjects'] = [{
            'user_id': s.user_id, 'user_email': s.user.email,
            'role': s.role, 'added_at': s.added_at,
        } for s in c.subjects.select_related('user').all()]
        out['events'] = [{
            'id': e.id, 'event_type': e.event_type,
            'actor_id': e.actor_id, 'actor_role': e.actor_role,
            'body': e.body, 'metadata': e.metadata,
            'created_at': e.created_at,
        } for e in c.events.order_by('created_at')]
    return out


class CaseListView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        qs = Case.objects.all().select_related('assigned_to').order_by('-created_at')
        qp = request.query_params
        if qp.get('status'):    qs = qs.filter(status=qp['status'])
        if qp.get('priority'):  qs = qs.filter(priority=qp['priority'])
        if qp.get('kind'):      qs = qs.filter(kind=qp['kind'])
        if qp.get('assigned_to'):
            qs = qs.filter(assigned_to_id=qp['assigned_to'])
        if qp.get('user'):
            # Cases involving this user — subject OR appearance as subject
            uid = qp['user']
            qs = qs.filter(
                Q(subject_type='user', subject_id=str(uid))
                | Q(subjects__user_id=uid)
            ).distinct()
        rows = qs[:100]
        return Response({
            'choices': {
                'status': [s for s, _ in CaseStatus.choices],
                'priority': [p for p, _ in CasePriority.choices],
                'kind': [k for k, _ in CaseKind.choices],
                'resolution': [r for r, _ in CaseResolution.choices],
            },
            'results': [_serialize_case(c) for c in rows],
        })

    def post(self, request):
        try:
            case = service.open_case(
                kind=request.data.get('kind') or 'other',
                title=request.data.get('title') or '(untitled)',
                priority=request.data.get('priority') or CasePriority.NORMAL,
                opened_by_admin=request.user,
                subject_type=request.data.get('subject_type') or '',
                subject_id=str(request.data.get('subject_id') or ''),
                summary=request.data.get('summary') or '',
            )
        except ValueError as e:
            return Response({'error': 'validation_error', 'detail': str(e)},
                            status=400)
        return Response(_serialize_case(case), status=201)


class CaseDetailView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request, pk):
        case = get_object_or_404(
            Case.objects.select_related('assigned_to')
            .prefetch_related('links', 'subjects__user', 'events'),
            pk=pk,
        )
        return Response(_serialize_case(case, deep=True))

    def patch(self, request, pk):
        case = get_object_or_404(Case, pk=pk)
        actions = []
        try:
            # Transition
            if 'status' in request.data:
                case = service.transition(
                    case, request.data['status'],
                    actor=request.user, actor_role='admin',
                    note=(request.data.get('note') or '')[:2000],
                    admin_override=bool(request.data.get('admin_override')),
                )
                actions.append('status')
            # Assign
            if 'assigned_to_id' in request.data:
                uid = request.data['assigned_to_id']
                target = None
                if uid:
                    from django.contrib.auth import get_user_model
                    target = get_user_model().objects.filter(pk=uid).first()
                case = service.assign(case, to_admin=target, by_actor=request.user)
                actions.append('assigned_to')
            # Priority
            if 'priority' in request.data:
                case = service.change_priority(
                    case, to_priority=request.data['priority'],
                    actor=request.user,
                )
                actions.append('priority')
        except service.TransitionError as e:
            return Response({'error': 'invalid_transition', 'detail': str(e)},
                            status=400)
        except ValueError as e:
            return Response({'error': 'validation_error', 'detail': str(e)},
                            status=400)
        return Response({'updated': actions, 'case': _serialize_case(case)})


class CaseResolveView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, pk):
        case = get_object_or_404(Case, pk=pk)
        try:
            case = service.resolve(
                case,
                resolution=request.data.get('resolution') or '',
                actor=request.user,
                note=(request.data.get('note') or '')[:2000],
            )
        except ValueError as e:
            return Response({'error': 'validation_error', 'detail': str(e)},
                            status=400)
        except service.TransitionError as e:
            return Response({'error': 'invalid_transition', 'detail': str(e)},
                            status=400)
        return Response(_serialize_case(case))


class CaseReopenView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, pk):
        case = get_object_or_404(Case, pk=pk)
        try:
            case = service.reopen(
                case, actor=request.user,
                note=(request.data.get('note') or '')[:2000],
            )
        except service.TransitionError as e:
            return Response({'error': 'invalid_transition', 'detail': str(e)},
                            status=400)
        return Response(_serialize_case(case))


class CaseLinkView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, pk):
        case = get_object_or_404(Case, pk=pk)
        link_type = (request.data.get('link_type') or '').strip()
        ref_type = (request.data.get('ref_type') or '').strip()
        ref_id = request.data.get('ref_id')
        if not (link_type and ref_type and ref_id is not None):
            return Response({'error': 'validation_error',
                             'detail': 'link_type, ref_type, ref_id required'},
                            status=400)
        link = service.add_link(
            case, link_type=link_type, ref_type=ref_type, ref_id=ref_id,
            note=(request.data.get('note') or '')[:300], actor=request.user,
        )
        return Response({'id': link.id, 'link_type': link.link_type,
                         'ref_type': link.ref_type, 'ref_id': link.ref_id},
                        status=201)

    def delete(self, request, pk, link_id):
        case = get_object_or_404(Case, pk=pk)
        ok = service.remove_link(case, link_id, actor=request.user)
        return Response({'removed': ok}, status=200 if ok else 404)


class CaseNoteView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, pk):
        case = get_object_or_404(Case, pk=pk)
        body = (request.data.get('body') or '').strip()
        if not body:
            return Response({'error': 'validation_error',
                             'detail': 'body required'}, status=400)
        ev = service.add_note(case, body=body, actor=request.user)
        return Response({'id': ev.id, 'created_at': ev.created_at,
                         'event_type': ev.event_type}, status=201)


class CaseSubjectView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, pk):
        case = get_object_or_404(Case, pk=pk)
        from django.contrib.auth import get_user_model
        uid = request.data.get('user_id')
        role = (request.data.get('role') or '').strip()
        if not uid or role not in {r for r, _ in CaseSubject.ROLES}:
            return Response({'error': 'validation_error'}, status=400)
        u = get_object_or_404(get_user_model(), pk=uid)
        sub = service.add_subject(case, user=u, role=role, actor=request.user)
        return Response({'user_id': sub.user_id, 'role': sub.role}, status=201)
