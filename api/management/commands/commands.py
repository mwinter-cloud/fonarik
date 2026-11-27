from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from api.models import LoginAttempt, AdminAction

class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        # логи входов старше 90 дней — удаляем
        cutoff = timezone.now() - timedelta(days=90)
        deleted, _ = LoginAttempt.objects.filter(created_at__lt=cutoff).delete()
        self.stdout.write(f'LoginAttempt deleted: {deleted}')

        # действия админов старше года — удаляем
        cutoff = timezone.now() - timedelta(days=365)
        deleted, _ = AdminAction.objects.filter(created_at__lt=cutoff).delete()
        self.stdout.write(f'AdminAction deleted: {deleted}')

