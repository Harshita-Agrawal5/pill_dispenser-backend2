from django.db import models
from django.contrib.auth.models import User


# ----------------- PROFILE -----------------
class Profile(models.Model):
    ROLE_CHOICES = (
        ('doctor', 'Doctor'),
        ('patient', 'Patient'),
        ('caregiver', 'Caregiver'),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)

    caregiver = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='patients',
        limit_choices_to={'profile__role': 'caregiver'}
    )

    # Profile detail fields
    age             = models.IntegerField(null=True, blank=True)
    gender          = models.CharField(max_length=10, blank=True)
    phone           = models.CharField(max_length=15, blank=True)
    address         = models.TextField(blank=True)
    medical_history = models.TextField(blank=True)

    # ✅ ONE prescription image per patient — upload once, visible to all
    prescription_image = models.ImageField(
        upload_to='prescriptions/',
        blank=True,
        null=True
    )

    # OCR-assisted readable version of the handwritten prescription.
    # ocr_text = raw machine-read guess (never shown as final/trusted on its own)
    # confirmed_text = what a doctor/caregiver has reviewed and corrected
    prescription_ocr_text = models.TextField(blank=True, null=True)
    prescription_confirmed_text = models.TextField(blank=True, null=True)
    prescription_confirmed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='prescriptions_confirmed'
    )
    prescription_confirmed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} ({self.role})"


# ----------------- MEDICINE -----------------
class Medicine(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('taken', 'Taken'),
        ('missed', 'Missed'),
    )

    patient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='medicines')
    name    = models.CharField(max_length=100)
    dosage  = models.CharField(max_length=50, blank=True, null=True)
    time    = models.TimeField()
    date    = models.DateField(auto_now_add=True)

    prescribed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='prescriptions'
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    notes  = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.name} for {self.patient.username} ({self.status})"


# ----------------- MEDICINE HISTORY -----------------
class MedicineHistory(models.Model):
    medicine  = models.ForeignKey(Medicine, on_delete=models.CASCADE, related_name='history')
    action    = models.CharField(max_length=20)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.medicine.name} {self.action}"


# ----------------- DISPENSER SLOT -----------------
class DispenserSlot(models.Model):
    patient           = models.ForeignKey(User, on_delete=models.CASCADE)
    medicine_name     = models.CharField(max_length=100)
    quantity          = models.IntegerField(default=0)
    expected_medicine = models.CharField(max_length=100)
    actual_medicine   = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"{self.medicine_name} - {self.patient.username}"


# ----------------- PILL EVENT (POSTMAN API LOG) -----------------
class PillEvent(models.Model):
    event_type    = models.CharField(max_length=50)
    message       = models.TextField(blank=True)
    patient_name  = models.CharField(max_length=100, null=True, blank=True)
    medicine_name = models.CharField(max_length=100, null=True, blank=True)
    timestamp     = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.event_type} - {self.patient_name or 'unknown'}"