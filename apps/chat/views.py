from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.contrib.auth import get_user_model
from .models import Chat, Message, MessageAttachment, QuickReplyTemplate
from apps.users.permissions import IsNotSuspended
from apps.accounts.models import Block

User=get_user_model()

def check_block(a,b):
    if Block.objects.filter(Q(blocker=a,blocked=b)|Q(blocker=b,blocked=a)).exists():
        raise PermissionDenied("You cannot communicate with this user.")

class MessageSerializer(serializers.ModelSerializer):
    sender_email=serializers.ReadOnlyField(source='sender.email')
    sender_name=serializers.SerializerMethodField()
    attachments=serializers.SerializerMethodField()
    class Meta:
        model=Message
        fields=['id','chat','sender','sender_email','sender_name','content','status','is_read','delivered_at','read_at','shared_product','shared_order','created_at','attachments']
        read_only_fields=['id','sender','status','is_read','delivered_at','read_at','created_at']
    def get_sender_name(self,obj):
        try: return obj.sender.profile.full_name
        except: return ''
    def get_attachments(self,obj):
        return [{'id':a.id,'file':a.file.url,'type':a.file_type} for a in obj.attachments.all()]

class ChatSerializer(serializers.ModelSerializer):
    buyer_email=serializers.ReadOnlyField(source='buyer.email')
    seller_email=serializers.ReadOnlyField(source='seller.email')
    last_message=serializers.SerializerMethodField()
    unread_count=serializers.SerializerMethodField()
    class Meta:
        model=Chat
        fields=['id','buyer','buyer_email','seller','seller_email','last_message','unread_count','last_message_at','created_at']
    def get_last_message(self,obj):
        msg=obj.messages.last()
        return {'content':msg.content[:80],'at':msg.created_at} if msg else None
    def get_unread_count(self,obj):
        user=self.context['request'].user
        return obj.messages.filter(is_read=False).exclude(sender=user).count()

class QuickReplySerializer(serializers.ModelSerializer):
    class Meta: model=QuickReplyTemplate; fields=['id','shortcut','message','created_at']
    
class ConversationListCreateView(generics.ListCreateAPIView):
    serializer_class=ChatSerializer
    permission_classes=[permissions.IsAuthenticated,IsNotSuspended]
    def get_queryset(self):
        user=self.request.user
        return Chat.objects.filter(Q(buyer=user)|Q(seller=user)).prefetch_related('messages').order_by('-last_message_at')
    def create(self,request,*args,**kwargs):
        seller_id=request.data.get('seller_id')
        if not seller_id: return Response({"detail":"seller_id required."},status=400)
        seller=get_object_or_404(User,pk=seller_id,is_seller=True)
        if request.user==seller: return Response({"detail":"Cannot chat with yourself."},status=400)
        check_block(request.user,seller)
        chat,created=Chat.objects.get_or_create(buyer=request.user,seller=seller)
        return Response(self.get_serializer(chat,context={'request':request}).data,status=201 if created else 200)

class MessageListCreateView(generics.ListCreateAPIView):
    serializer_class=MessageSerializer
    permission_classes=[permissions.IsAuthenticated,IsNotSuspended]
    def _chat(self):
        chat=get_object_or_404(Chat,pk=self.kwargs['conversation_id'])
        if self.request.user not in(chat.buyer,chat.seller): raise PermissionDenied("Not a participant.")
        return chat
    def get_queryset(self):
        chat=self._chat()
        other=chat.seller if self.request.user==chat.buyer else chat.buyer
        check_block(self.request.user,other)
        Message.objects.filter(chat=chat,is_read=False).exclude(sender=self.request.user).update(is_read=True,read_at=timezone.now(),status='read')
        return Message.objects.filter(chat=chat).prefetch_related('attachments')
    def perform_create(self,s):
        chat=self._chat()
        other=chat.seller if self.request.user==chat.buyer else chat.buyer
        check_block(self.request.user,other)
        msg=s.save(chat=chat,sender=self.request.user)
        chat.last_message_at=timezone.now(); chat.save()

class MarkReadView(APIView):
    permission_classes=[permissions.IsAuthenticated]
    def post(self,request,conversation_id):
        chat=get_object_or_404(Chat,pk=conversation_id)
        if request.user not in(chat.buyer,chat.seller): return Response({"detail":"Not a participant."},status=403)
        updated=Message.objects.filter(chat=chat,is_read=False).exclude(sender=request.user).update(is_read=True,read_at=timezone.now(),status='read')
        return Response({"marked_read":updated})

class ArchiveChatView(APIView):
    permission_classes=[permissions.IsAuthenticated]
    def post(self,request,conversation_id):
        chat=get_object_or_404(Chat,pk=conversation_id)
        user=request.user
        if user==chat.buyer: chat.is_archived_by_buyer=True
        elif user==chat.seller: chat.is_archived_by_seller=True
        else: return Response({"detail":"Not a participant."},status=403)
        chat.save()
        return Response({"detail":"Chat archived."})

class QuickReplyListCreateView(generics.ListCreateAPIView):
    serializer_class=QuickReplySerializer
    permission_classes=[permissions.IsAuthenticated,IsNotSuspended]
    def get_queryset(self): return QuickReplyTemplate.objects.filter(seller=self.request.user)
    def perform_create(self,s): s.save(seller=self.request.user)

class ReportConversationView(APIView):
    permission_classes=[permissions.IsAuthenticated,IsNotSuspended]
    def post(self,request,conversation_id):
        chat=get_object_or_404(Chat,pk=conversation_id)
        user=request.user
        if user not in(chat.buyer,chat.seller): return Response({"detail":"Not a participant."},status=403)
        reason=request.data.get('reason','').strip()
        if not reason: return Response({"detail":"Reason required."},status=400)
        other=chat.seller if user==chat.buyer else chat.buyer
        from apps.reports.models import Report
        Report.objects.get_or_create(reporter=user,target_type='seller',target_id=other.id,defaults={'reason':reason})
        return Response({"detail":"Reported."})
