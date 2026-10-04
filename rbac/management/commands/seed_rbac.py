from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from rbac import services
from rbac.models import Permission, Role, RolePermission, UserRole

PERMISSIONS = {
    "roles.manage": "Rollarni boshqarish",
    "permissions.manage": "Ruxsatlarni boshqarish",
    "users.view_access": "Boshqa userlar dostupini ko'rish",
    "users.view": "Foydalanuvchilarni ko'rish",
    "users.create": "Foydalanuvchi yaratish",
    "users.update": "Foydalanuvchini tahrirlash",
    "users.delete": "Foydalanuvchini o'chirish (nofaol qilish)",
    "loans.view": "Kreditlarni ko'rish",
    "loans.approve": "Kreditni tasdiqlash",
    "loans.reject": "Kreditni rad etish",
    "reports.view": "Hisobotlarni ko'rish",
    "reports.export": "Hisobotlarni eksport qilish",
}

ROLES = {
    "super_admin": ("Super admin", True, []),
    "admin": ("Administrator", False, list(PERMISSIONS)),
    "manager": (
        "Menejer",
        False,
        ["users.view", "loans.view", "loans.approve", "loans.reject", "reports.view", "reports.export"],
    ),
    "operator": ("Operator", False, ["users.view", "loans.view"]),
    "viewer": ("Kuzatuvchi", False, ["users.view", "loans.view", "reports.view"]),
}


class Command(BaseCommand):
    help = "Standart rollar va permissionlarni yaratadi (qayta ishga tushirsa bo'ladi)"

    def add_arguments(self, parser):
        parser.add_argument("--admin", help="Shu username'ga super_admin rolini biriktirish")

    @transaction.atomic
    def handle(self, *args, **options):
        # Only missing records are created; anything changed through the API is left as is
        perms = {}
        new_perms = 0
        for codename, display_name in PERMISSIONS.items():
            perms[codename], created = Permission.objects.get_or_create(
                codename=codename, defaults={"display_name": display_name}
            )
            new_perms += created

        new_roles = 0
        for name, (display_name, is_super, codenames) in ROLES.items():
            role, created = Role.objects.get_or_create(
                name=name, defaults={"display_name": display_name, "is_super_admin": is_super}
            )
            if created:
                RolePermission.objects.bulk_create(RolePermission(role=role, permission=perms[c]) for c in codenames)
                new_roles += 1

        self.stdout.write(f"Yangi permissionlar: {new_perms}, yangi rollar: {new_roles}")

        self._create_admin_from_env()

        username = options.get("admin")
        if username:
            user = get_user_model().objects.filter(username=username).first()
            if user is None:
                raise CommandError(f"'{username}' topilmadi")
            UserRole.objects.get_or_create(user=user, role=Role.objects.get(name="super_admin"))
            services.invalidate_users([user.id])
            self.stdout.write(f"{username} -> super_admin")

        self.stdout.write(self.style.SUCCESS("Tayyor"))

    def _create_admin_from_env(self):
        username, password = settings.ADMIN_USERNAME, settings.ADMIN_PASSWORD
        if not username or not password:
            return
        User = get_user_model()
        if User.objects.filter(username=username).exists():
            return
        user = User.objects.create_superuser(username=username, password=password)
        UserRole.objects.create(user=user, role=Role.objects.get(name="super_admin"))
        self.stdout.write(f"Admin yaratildi: {username} (super_admin)")
