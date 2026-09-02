from django.contrib import admin
from django.contrib import admin
from .models import Profile, Medicine, MedicineHistory
from .models import DispenserSlot

admin.site.register(DispenserSlot)
# Profile admin to show caregiver assignment
@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'caregiver')   # Shows these columns in admin
    list_filter = ('role',)                        # Filter by role
    search_fields = ('user__username',)           # Search by username

# Medicine admin
@admin.register(Medicine)
class MedicineAdmin(admin.ModelAdmin):
    list_display = ('name', 'patient', 'time', 'status')
    list_filter = ('status', 'time')
    search_fields = ('name', 'patient__username')

# MedicineHistory admin
@admin.register(MedicineHistory)
class MedicineHistoryAdmin(admin.ModelAdmin):
    list_display = ('medicine', 'action', 'timestamp')
    list_filter = ('action',)
# Register your models here.


from django.contrib import admin
from .models import PillEvent

admin.site.register(PillEvent)
