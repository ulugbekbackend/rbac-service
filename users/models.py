from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """
    Loyihaning user modeli. Hozircha standart maydonlar yetarli
    (username, password, email, first_name, last_name, is_active ...),
    kerak bo'lsa yangi maydonlar shu yerga qo'shiladi.
    Rollar va permissionlar rbac app'ida: UserRole, UserPermission.
    """

    class Meta:
        db_table = "users"
        ordering = ["id"]

    def __str__(self):
        return self.username
