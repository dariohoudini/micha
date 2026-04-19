"""
Chat WebSocket Consumer — Fixed
FIX: Message size limit — prevents 50MB string from crashing the server.
FIX: Rate limiting on messages per connection.
FIX: Proper error handling so one bad message doesn't kill the connection.
"""
import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone

logger = logging.getLogger('micha')

# FIX: Limits
MAX_MESSAGE_LENGTH = 5000   # 5,000 characters max per message
MAX_MESSAGES_PER_MINUTE = 30  # Rate limit: 30 messages/minute per connection


class ChatConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.conversation_id = self.scope['url_route']['kwargs']['conversation_id']
        self.room_group = f'chat_{self.conversation_id}'
        self.user = self.scope['user']
        self._message_count = 0
        self._rate_window_start = timezone.now()

        # FIX: Verify user is authenticated before accepting WebSocket
        if not self.user.is_authenticated:
            logger.warning(f"Unauthenticated WebSocket connection attempt to chat {self.conversation_id}")
            await self.close(code=4001)
            return

        if not await self.is_participant():
            logger.warning(f"Non-participant WebSocket connection: user {self.user.id} → chat {self.conversation_id}")
            await self.close(code=4003)
            return

        await self.channel_layer.group_add(self.room_group, self.channel_name)
        await self.accept()

        await self.channel_layer.group_send(self.room_group, {
            'type': 'user.online',
            'user_id': self.user.id,
        })
        logger.info(f"WebSocket connected: user {self.user.id} → chat {self.conversation_id}")

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group, self.channel_name)
        logger.info(f"WebSocket disconnected: user {self.user.id} → chat {self.conversation_id} (code={close_code})")

    async def receive(self, text_data):
        # FIX: Rate limiting per connection
        now = timezone.now()
        seconds_in_window = (now - self._rate_window_start).total_seconds()
        if seconds_in_window < 60:
            self._message_count += 1
            if self._message_count > MAX_MESSAGES_PER_MINUTE:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'error': 'rate_limited',
                    'detail': 'Too many messages. Please slow down.',
                }))
                return
        else:
            # Reset rate window
            self._message_count = 1
            self._rate_window_start = now

        # FIX: Message size limit
        if len(text_data) > MAX_MESSAGE_LENGTH * 2:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': 'message_too_large',
                'detail': f'Message too large. Maximum {MAX_MESSAGE_LENGTH} characters.',
            }))
            return

        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': 'invalid_json',
                'detail': 'Message must be valid JSON.',
            }))
            return

        msg_type = data.get('type', 'message')

        if msg_type == 'message':
            content = data.get('content', '').strip()
            if not content:
                return

            # FIX: Enforce content length limit
            if len(content) > MAX_MESSAGE_LENGTH:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'error': 'content_too_long',
                    'detail': f'Message must be under {MAX_MESSAGE_LENGTH} characters.',
                }))
                return

            message = await self.save_message(
                content,
                data.get('shared_product_id'),
                data.get('shared_order_id'),
            )
            await self.channel_layer.group_send(self.room_group, {
                'type': 'chat.message',
                'message_id': message.id,
                'content': content,
                'sender_id': self.user.id,
                'sender_name': await self.get_name(),
                'created_at': message.created_at.isoformat(),
                'shared_product_id': data.get('shared_product_id'),
                'shared_order_id': data.get('shared_order_id'),
            })

        elif msg_type == 'typing':
            await self.channel_layer.group_send(self.room_group, {
                'type': 'typing.indicator',
                'user_id': self.user.id,
                'is_typing': bool(data.get('is_typing')),
            })

        elif msg_type == 'read':
            await self.mark_read()
            await self.channel_layer.group_send(self.room_group, {
                'type': 'messages.read',
                'user_id': self.user.id,
            })

    # ── Event handlers ────────────────────────────────────────────────────────

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'message',
            'message_id': event['message_id'],
            'content': event['content'],
            'sender_id': event['sender_id'],
            'sender_name': event['sender_name'],
            'created_at': event['created_at'],
            'shared_product_id': event.get('shared_product_id'),
            'shared_order_id': event.get('shared_order_id'),
        }))

    async def typing_indicator(self, event):
        if event['user_id'] != self.user.id:
            await self.send(text_data=json.dumps({
                'type': 'typing',
                'user_id': event['user_id'],
                'is_typing': event['is_typing'],
            }))

    async def messages_read(self, event):
        await self.send(text_data=json.dumps({
            'type': 'read',
            'user_id': event['user_id'],
        }))

    async def user_online(self, event):
        await self.send(text_data=json.dumps({
            'type': 'online',
            'user_id': event['user_id'],
        }))

    # ── DB helpers ────────────────────────────────────────────────────────────

    @database_sync_to_async
    def is_participant(self):
        from apps.chat.models import Chat
        try:
            chat = Chat.objects.get(pk=self.conversation_id)
            return self.user.is_authenticated and self.user in (chat.buyer, chat.seller)
        except Chat.DoesNotExist:
            return False

    @database_sync_to_async
    def save_message(self, content, shared_product_id=None, shared_order_id=None):
        from apps.chat.models import Chat, Message
        chat = Chat.objects.get(pk=self.conversation_id)
        msg = Message.objects.create(
            chat=chat,
            sender=self.user,
            content=content,
            shared_product_id=shared_product_id,
            shared_order_id=shared_order_id,
        )
        chat.last_message_at = timezone.now()
        chat.save(update_fields=['last_message_at'])
        return msg

    @database_sync_to_async
    def mark_read(self):
        from apps.chat.models import Chat, Message
        chat = Chat.objects.get(pk=self.conversation_id)
        Message.objects.filter(
            chat=chat, is_read=False
        ).exclude(sender=self.user).update(
            is_read=True, read_at=timezone.now(), status='read'
        )

    @database_sync_to_async
    def get_name(self):
        try:
            return self.user.profile.full_name or self.user.email
        except Exception:
            return self.user.email
