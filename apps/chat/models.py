from django.db import models
from django.conf import settings
User = settings.AUTH_USER_MODEL

class Chat(models.Model):
    buyer=models.ForeignKey(User,on_delete=models.CASCADE,related_name='chats_as_buyer')
    seller=models.ForeignKey(User,on_delete=models.CASCADE,related_name='chats_as_seller')
    is_archived_by_buyer=models.BooleanField(default=False)
    is_archived_by_seller=models.BooleanField(default=False)
    is_muted_by_buyer=models.BooleanField(default=False)
    is_muted_by_seller=models.BooleanField(default=False)
    last_message_at=models.DateTimeField(null=True,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta: unique_together=('buyer','seller'); ordering=['-last_message_at']

class Message(models.Model):
    STATUS=(('sent','Sent'),('delivered','Delivered'),('read','Read'))
    chat=models.ForeignKey(Chat,on_delete=models.CASCADE,related_name='messages')
    sender=models.ForeignKey(User,on_delete=models.CASCADE,related_name='sent_messages')
    content=models.TextField(blank=True)
    status=models.CharField(max_length=10,choices=STATUS,default='sent')
    is_read=models.BooleanField(default=False)
    delivered_at=models.DateTimeField(null=True,blank=True)
    read_at=models.DateTimeField(null=True,blank=True)
    shared_product=models.ForeignKey('products.Product',on_delete=models.SET_NULL,null=True,blank=True,related_name='chat_shares')
    shared_order=models.ForeignKey('orders.Order',on_delete=models.SET_NULL,null=True,blank=True,related_name='chat_shares')
    is_quick_reply=models.BooleanField(default=False)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=['created_at']

class MessageAttachment(models.Model):
    message=models.ForeignKey(Message,on_delete=models.CASCADE,related_name='attachments')
    file=models.FileField(upload_to='chat/attachments/')
    file_type=models.CharField(max_length=20,blank=True)
    uploaded_at=models.DateTimeField(auto_now_add=True)

class QuickReplyTemplate(models.Model):
    seller=models.ForeignKey(User,on_delete=models.CASCADE,related_name='quick_replies')
    shortcut=models.CharField(max_length=50)
    message=models.TextField()
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta: unique_together=('seller','shortcut')
