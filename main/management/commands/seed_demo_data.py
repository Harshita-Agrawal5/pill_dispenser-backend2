"""
Seed realistic demo data so the dashboard never looks empty during a
presentation. Safe to run multiple times — uses get_or_create throughout.

Usage:
    python3 manage.py seed_demo_data
"""
import datetime
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from main.models import Profile, Medicine, MedicineHistory, DispenserSlot


class Command(BaseCommand):
    help = "Seed realistic demo data (doctor, caregiver, patients, medicines) for presentations."

    def handle(self, *args, **options):
        # ---------------- USERS ----------------
        doctor = self._make_user('dr_mehta', 'demo1234', 'doctor')
        caregiver = self._make_user('caregiver_asha', 'demo1234', 'caregiver')
        patient1 = self._make_user('patient_ramesh', 'demo1234', 'patient')
        patient2 = self._make_user('patient_sunita', 'demo1234', 'patient')

        # link patients to caregiver
        for p in (patient1, patient2):
            profile = p.profile
            profile.caregiver = caregiver
            profile.age = 68 if p == patient1 else 72
            profile.gender = 'Male' if p == patient1 else 'Female'
            profile.phone = '9876543210'
            profile.address = 'Bengaluru, Karnataka'
            profile.medical_history = 'Hypertension, Type 2 Diabetes' if p == patient1 else 'Arthritis'
            profile.save()

        self.stdout.write(self.style.SUCCESS(
            f"Users ready: doctor={doctor.username}, caregiver={caregiver.username}, "
            f"patients={patient1.username}, {patient2.username} (all passwords: demo1234)"
        ))

        # ---------------- MEDICINES ----------------
        now = datetime.datetime.now()
        past_time = (now - datetime.timedelta(hours=2)).time()   # overdue -> triggers missed-dose alert
        soon_time = (now + datetime.timedelta(minutes=2)).time()  # about to trigger reminder/voice demo
        morning = datetime.time(9, 0)
        evening = datetime.time(20, 0)

        demo_meds = [
            (patient1, 'Metformin', '500mg', morning, 'taken'),
            (patient1, 'Amlodipine', '5mg', evening, 'pending'),
            (patient1, 'Atorvastatin', '10mg', past_time, 'pending'),   # will show as overdue
            (patient2, 'Paracetamol', '650mg', soon_time, 'pending'),   # will trigger the reminder demo
            (patient2, 'Calcium + D3', '1 tablet', morning, 'missed'),
        ]

        for patient, name, dosage, time, status in demo_meds:
            med, created = Medicine.objects.get_or_create(
                patient=patient, name=name, time=time,
                defaults={'dosage': dosage, 'status': status, 'prescribed_by': doctor, 'notes': ''}
            )
            if not created:
                med.status = status
                med.dosage = dosage
                med.save()
            if status in ('taken', 'missed'):
                MedicineHistory.objects.get_or_create(medicine=med, action=status)

        self.stdout.write(self.style.SUCCESS(f"Seeded {len(demo_meds)} medicines across 2 patients."))

        # ---------------- DISPENSER SLOTS ----------------
        demo_slots = [
            (patient1, 'Metformin', 12, 'Metformin', 'Metformin'),
            (patient1, 'Atorvastatin', 2, 'Atorvastatin', 'Atorvastatin'),   # low stock -> good refill demo
            (patient2, 'Paracetamol', 20, 'Paracetamol', 'Paracetamol'),
        ]
        for patient, med_name, qty, expected, actual in demo_slots:
            DispenserSlot.objects.update_or_create(
                patient=patient, medicine_name=med_name,
                defaults={'quantity': qty, 'expected_medicine': expected, 'actual_medicine': actual},
            )
        self.stdout.write(self.style.SUCCESS(f"Seeded {len(demo_slots)} dispenser slots."))

        self.stdout.write(self.style.SUCCESS(
            "\nDemo data ready. Suggested login for the walkthrough:\n"
            "  Patient:   patient_sunita / demo1234   (has a reminder firing in ~2 min for the voice demo)\n"
            "  Caregiver: caregiver_asha / demo1234   (has an overdue-dose alert + a low-stock slot to refill)\n"
            "  Doctor:    dr_mehta / demo1234          (web dashboard only)\n"
        ))

    def _make_user(self, username, password, role):
        user, _ = User.objects.get_or_create(username=username)
        user.set_password(password)
        user.save()
        Profile.objects.get_or_create(user=user, defaults={'role': role})
        return user
