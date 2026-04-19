from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from .models import UserProfile, Role

User=settings.AUTH_USER_MODEL

@receiver(post_save,sender=User)
def create_user_profile(sender,instance,created,**kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)
        consumer_role,_=Role.objects.get_or_create(name=Role.CONSUMER,defaults={'description':'Default consumer role'})
        instance.roles.add(consumer_role)
