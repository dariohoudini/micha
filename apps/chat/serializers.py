from rest_framework import serializers
from .models import Chat, Message, MessageAttachment


class MessageAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessageAttachment
        fields = ['id', 'file', 'uploaded_at']


class MessageSerializer(serializers.ModelSerializer):
    # FIXED: was referencing sender.username — User model uses email, not username
    sender_email = serializers.ReadOnlyField(source='sender.email')
    sender_name = serializers.ReadOnlyField(source='sender.full_name')
    attachments = MessageAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = Message
        fields = [
            'id', 'chat', 'sender', 'sender_email', 'sender_name',
            'content', 'is_read', 'attachments', 'created_at',
        ]
        read_only_fields = ['id', 'sender', 'sender_email', 'sender_name', 'created_at']


class ChatSerializer(serializers.ModelSerializer):
    # FIXED: was referencing buyer.username / seller.username
    buyer_email = serializers.ReadOnlyField(source='buyer.email')
    buyer_name = serializers.ReadOnlyField(source='buyer.full_name')
    seller_email = serializers.ReadOnlyField(source='seller.email')
    seller_name = serializers.ReadOnlyField(source='seller.full_name')
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = Chat
        fields = [
            'id', 'buyer', 'buyer_email', 'buyer_name',
            'seller', 'seller_email', 'seller_name',
            'last_message', 'unread_count', 'created_at',
        ]
        read_only_fields = ['id', 'buyer', 'created_at']

    def get_last_message(self, obj):
        msg = obj.messages.last()
        if msg:
            return {'content': msg.content[:80], 'created_at': msg.created_at}
        return None

    def get_unread_count(self, obj):
        user = self.context['request'].user
        # Count messages not sent by the current user that are unread
        return obj.messages.filter(is_read=False).exclude(sender=user).count()
