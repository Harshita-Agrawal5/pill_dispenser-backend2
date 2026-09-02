from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages

from rest_framework.decorators import api_view, authentication_classes
from rest_framework.response import Response
from rest_framework.authentication import SessionAuthentication

from .models import Profile, Medicine, MedicineHistory, DispenserSlot, PillEvent


class CsrfExemptSessionAuthentication(SessionAuthentication):
    """
    Session auth without CSRF enforcement.
    Needed because the Flutter app authenticates via the session cookie
    (simple, capstone-appropriate — no JWT) but can't easily carry a
    browser-style CSRF token. Safe here because these endpoints are only
    reachable with a valid, already-authenticated session cookie anyway.
    """
    def enforce_csrf(self, request):
        return  # skip CSRF check


# ----------------- SAFE PROFILE GET -----------------
def get_user_role(user):
    profile, created = Profile.objects.get_or_create(user=user)
    return profile


# ----------------- DASHBOARD REDIRECT -----------------
def redirect_dashboard(user):
    profile = get_user_role(user)
    if profile.role == 'doctor':
        return redirect('doctor_dashboard')
    elif profile.role == 'patient':
        return redirect('user_dashboard')
    elif profile.role == 'caregiver':
        return redirect('caregiver_dashboard')
    else:
        return redirect('login')


def redirect_user(request):
    if request.user.is_authenticated:
        return redirect_dashboard(request.user)
    return redirect('login')


# ----------------- AUTH -----------------
def login_view(request):
    if request.method == "POST":
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect_dashboard(user)
        else:
            return render(request, 'main/login.html', {'error': 'Invalid credentials'})
    return render(request, 'main/login.html')


def signup_view(request):
    if request.method == "POST":
        username = request.POST['username']
        password = request.POST['password']
        role = request.POST.get('role', '').lower()
        if not role:
            return render(request, 'main/signup.html', {'error': 'Please select a role'})
        if User.objects.filter(username=username).exists():
            return render(request, 'main/signup.html', {'error': 'User already exists'})
        user = User.objects.create_user(username=username, password=password)
        Profile.objects.create(user=user, role=role)
        return redirect('login')
    return render(request, 'main/signup.html')


@login_required
def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def home(request):
    return redirect_dashboard(request.user)


# ----------------- DOCTOR DASHBOARD -----------------
@login_required
def doctor_dashboard(request):
    profile = get_user_role(request.user)
    if profile.role != 'doctor':
        return redirect('home')
    patients = User.objects.filter(profile__role='patient')
    return render(request, 'main/doctor_dashboard.html', {'patients': patients})


@login_required
def patient_detail(request, patient_id):
    profile = get_user_role(request.user)
    if profile.role != 'doctor':
        return redirect('home')
    patient       = get_object_or_404(User, id=patient_id, profile__role='patient')
    medicines     = Medicine.objects.filter(patient=patient).order_by('time')
    taken_count   = medicines.filter(status='taken').count()
    missed_count  = medicines.filter(status='missed').count()
    pending_count = medicines.count() - taken_count - missed_count

    # ✅ pass patient's profile so doctor can see prescription image
    patient_profile = patient.profile

    return render(request, 'main/patient_detail.html', {
        'patient':         patient,
        'patient_profile': patient_profile,
        'medicines':       medicines,
        'taken_count':     taken_count,
        'missed_count':    missed_count,
        'pending_count':   pending_count,
    })


# ----------------- UNIFIED ADD MEDICINE (Doctor / Patient / Caregiver) -----------------
@login_required
def add_medicine(request, patient_id=None):
    profile = get_user_role(request.user)
    role    = profile.role

    if role == 'doctor':
        if not patient_id:
            return redirect('doctor_dashboard')
        patient = get_object_or_404(User, id=patient_id, profile__role='patient')
    elif role == 'patient':
        patient = request.user
    elif role == 'caregiver':
        if not patient_id:
            return redirect('caregiver_dashboard')
        patient = get_object_or_404(User, id=patient_id, profile__role='patient')
    else:
        return redirect('home')

    if request.method == "POST":
        name   = request.POST.get('name',   '').strip()
        dosage = request.POST.get('dosage', '').strip()
        time   = request.POST.get('time',   '').strip()
        notes  = request.POST.get('notes',  '').strip()

        if not name or not dosage or not time:
            messages.error(request, "Please fill all required fields!")
            return redirect(request.path)

        med = Medicine.objects.create(
            patient       = patient,
            name          = name,
            dosage        = dosage,
            time          = time,
            notes         = notes,
            prescribed_by = request.user,
            status        = 'pending',
        )
        MedicineHistory.objects.create(medicine=med, action='pending')
        messages.success(request, f"Medicine '{name}' added successfully!")

        if role == 'doctor':
            return redirect('patient_detail', patient_id=patient.id)
        elif role == 'caregiver':
            return redirect('caregiver_dashboard')
        else:
            return redirect('user_dashboard')

    return render(request, 'main/add_medicine.html', {
        'patient': patient,
        'role':    role,
    })


# ----------------- PATIENT DASHBOARD -----------------
@login_required
def user_dashboard(request):
    profile = get_user_role(request.user)
    if profile.role != 'patient':
        return redirect('home')

    user      = request.user
    medicines = Medicine.objects.filter(patient=user).order_by('-id')

    print("DASHBOARD MEDICINES:", list(medicines.values('name', 'status')))

    taken_count   = medicines.filter(status='taken').count()
    missed_count  = medicines.filter(status='missed').count()
    pending_count = medicines.count() - taken_count - missed_count
    caregivers    = User.objects.filter(profile__role='caregiver')

    print("USER:", request.user.username)
    print("MEDICINES:", list(Medicine.objects.filter(patient=request.user).values('name', 'status')))

    if request.method == 'POST' and 'caregiver' in request.POST:
        caregiver_id = request.POST.get('caregiver')
        if caregiver_id:
            caregiver_user = User.objects.get(id=caregiver_id)
            profile.caregiver = caregiver_user
            profile.save()
            return redirect('user_dashboard')

    profile.refresh_from_db()

    from collections import defaultdict
    from django.utils import timezone

    grouped_medicines = defaultdict(list)
    for med in medicines:
        date = med.created_at.date() if hasattr(med, 'created_at') else timezone.now().date()
        grouped_medicines[date].append(med)
    grouped_medicines = dict(sorted(grouped_medicines.items(), reverse=True))

    today     = timezone.now().date()
    yesterday = today - timezone.timedelta(days=1)

    return render(request, 'main/user_dashboard.html', {
        'medicines':         medicines,
        'taken_count':       taken_count,
        'missed_count':      missed_count,
        'pending_count':     pending_count,
        'profile':           profile,
        'caregivers':        caregivers,
        'grouped_medicines': grouped_medicines,
        'today':             today,
        'yesterday':         yesterday,
    })


# ----------------- CAREGIVER DASHBOARD -----------------
@login_required
def caregiver_dashboard(request):
    profile = get_user_role(request.user)
    if profile.role != 'caregiver':
        return redirect('home')

    patients  = User.objects.filter(profile__caregiver=request.user)
    medicines = Medicine.objects.filter(patient__in=patients).order_by('time')

    taken_count   = medicines.filter(status='taken').count()
    missed_count  = medicines.filter(status='missed').count()
    pending_count = medicines.count() - taken_count - missed_count

    # ----- Missed-dose escalation: pending medicines overdue by 30+ mins -----
    from datetime import datetime, timedelta
    from django.utils import timezone

    overdue_medicines = []
    now = timezone.localtime()
    for med in medicines.filter(status='pending'):
        scheduled_dt = datetime.combine(med.date, med.time)
        if timezone.is_naive(scheduled_dt):
            scheduled_dt = timezone.make_aware(scheduled_dt)
        if now > scheduled_dt + timedelta(minutes=30):
            overdue_medicines.append(med)

    return render(request, 'main/caregiver_dashboard.html', {
        'patients':          patients,
        'medicines':         medicines,
        'taken_count':       taken_count,
        'missed_count':      missed_count,
        'pending_count':     pending_count,
        'overdue_medicines': overdue_medicines,
    })


# ----------------- MEDICINE HISTORY -----------------
@login_required
def medicine_history(request, patient_id=None):
    profile = get_user_role(request.user)
    role    = profile.role

    if role == 'doctor':
        medicines = Medicine.objects.filter(prescribed_by=request.user)
        if patient_id:
            medicines = medicines.filter(patient__id=patient_id)
    elif role == 'patient':
        medicines = Medicine.objects.filter(patient=request.user)
    elif role == 'caregiver':
        medicines = Medicine.objects.filter(patient__profile__caregiver=request.user)
    else:
        return redirect('home')

    history = MedicineHistory.objects.filter(medicine__in=medicines).order_by('-timestamp')
    return render(request, 'main/medicine_history.html', {'history': history, 'role': role})


# ----------------- DISPENSER -----------------
@login_required
def dispenser_status(request):
    profile = get_user_role(request.user)
    role    = profile.role
    if role not in ['patient', 'caregiver']:
        return redirect('home')
    if role == 'patient':
        slots = DispenserSlot.objects.filter(patient=request.user)
    else:
        slots = DispenserSlot.objects.filter(patient__profile__caregiver=request.user)
    return render(request, 'main/dispenser_status.html', {'slots': slots, 'role': role})


# =================================================================
# ✅ PRESCRIPTION IMAGE — upload / delete
# ONE image per patient. Visible to patient, caregiver, doctor.
# Upload page is separate — not part of add medicine form.
# =================================================================
@login_required
def upload_prescription(request, patient_id=None):
    """
    Any role can upload/replace the prescription image for a patient.
    Patient uploads for themselves.
    Doctor/Caregiver pass patient_id.
    """
    profile = get_user_role(request.user)
    role    = profile.role

    if role == 'patient':
        patient = request.user
    elif role in ('doctor', 'caregiver'):
        if not patient_id:
            return redirect('home')
        patient = get_object_or_404(User, id=patient_id, profile__role='patient')
    else:
        return redirect('home')

    patient_profile = patient.profile

    if request.method == 'POST':
        image = request.FILES.get('prescription_image')
        if image:
            # replace old image
            patient_profile.prescription_image = image
            patient_profile.save()
            messages.success(request, "Prescription image uploaded successfully!")
        else:
            messages.error(request, "Please select an image to upload.")
        # redirect back to where they came from
        if role == 'doctor':
            return redirect('patient_detail', patient_id=patient.id)
        elif role == 'caregiver':
            return redirect('caregiver_dashboard')
        else:
            return redirect('user_dashboard')

    return render(request, 'main/upload_prescription.html', {
        'patient':         patient,
        'patient_profile': patient_profile,
        'role':            role,
    })


@login_required
def delete_prescription(request, patient_id=None):
    """Delete the prescription image for a patient."""
    profile = get_user_role(request.user)
    role    = profile.role

    if role == 'patient':
        patient = request.user
    elif role in ('doctor', 'caregiver'):
        if not patient_id:
            return redirect('home')
        patient = get_object_or_404(User, id=patient_id, profile__role='patient')
    else:
        return redirect('home')

    patient_profile = patient.profile
    patient_profile.prescription_image = None
    patient_profile.save()
    messages.success(request, "Prescription image removed.")

    if role == 'doctor':
        return redirect('patient_detail', patient_id=patient.id)
    elif role == 'caregiver':
        return redirect('caregiver_dashboard')
    else:
        return redirect('user_dashboard')


# ----------------- API (POSTMAN INTEGRATION) -----------------
@api_view(['POST'])
def pill_event(request):
    event         = request.data.get("event")
    patient_name  = request.data.get("patient_name")
    medicine_name = request.data.get("medicine_name")

    if not (event and patient_name and medicine_name):
        return Response({"error": "Missing data"})

    patient = User.objects.filter(username__iexact=patient_name.strip()).first()
    if not patient:
        return Response({"error": "Patient not found"})

    from datetime import datetime
    med = Medicine.objects.create(
        patient=patient,
        name=medicine_name.strip(),
        time=datetime.now().time(),
        status="taken" if event == "pill_taken" else "missed"
    )
    MedicineHistory.objects.create(medicine=med, action=event)

    slot = DispenserSlot.objects.filter(
        patient=patient,
        medicine_name__iexact=medicine_name.strip()
    ).first()
    if slot:
        if slot.quantity > 0:
            slot.quantity -= 1
            slot.save()
    return Response({"message": "New entry created", "medicine": med.name, "status": med.status})


# ----------------- DASHBOARD (EVENT VIEW) -----------------
def dashboard(request):
    events = PillEvent.objects.order_by('-timestamp')[:10]
    return render(request, "dashboard.html", {"events": events})


@login_required
def take_medicine(request, med_id):
    profile = get_user_role(request.user)
    med = get_object_or_404(Medicine, id=med_id)

    if profile.role == 'patient':
        if med.patient != request.user:
            return redirect('home')
        redirect_to = 'user_dashboard'
    elif profile.role == 'caregiver':
        if med.patient.profile.caregiver != request.user:
            return redirect('home')
        redirect_to = 'caregiver_dashboard'
    else:
        return redirect('home')

    med.status = 'taken'
    med.save()
    MedicineHistory.objects.create(medicine=med, action='taken')
    return redirect(redirect_to)


@login_required
def mark_missed(request, med_id):
    profile = get_user_role(request.user)
    med = get_object_or_404(Medicine, id=med_id)

    if profile.role == 'patient':
        if med.patient != request.user:
            return redirect('home')
        redirect_to = 'user_dashboard'
    elif profile.role == 'caregiver':
        if med.patient.profile.caregiver != request.user:
            return redirect('home')
        redirect_to = 'caregiver_dashboard'
    else:
        return redirect('home')

    med.status = 'missed'
    med.save()
    MedicineHistory.objects.create(medicine=med, action='missed')
    return redirect(redirect_to)


# ----------------- CAREGIVER: REFILL DISPENSER SLOT -----------------
@login_required
def refill_slot(request, slot_id):
    profile = get_user_role(request.user)
    if profile.role != 'caregiver':
        return redirect('home')

    slot = get_object_or_404(DispenserSlot, id=slot_id, patient__profile__caregiver=request.user)

    if request.method == 'POST':
        new_qty = request.POST.get('quantity', '').strip()
        if new_qty.isdigit():
            slot.quantity = int(new_qty)
            slot.save()
            messages.success(request, f"{slot.medicine_name} refilled to {slot.quantity}.")
        else:
            messages.error(request, "Please enter a valid quantity.")

    return redirect('dispenser_status')


# =================================================================
# API 1 — PATIENT STATUS
# =================================================================
@api_view(['GET'])
def patient_status(request):
    patient_name = request.query_params.get("name")
    if not patient_name:
        return Response({"error": "Please provide ?name=patient_username"})
    patient = User.objects.filter(username__iexact=patient_name.strip()).first()
    if not patient:
        return Response({"error": "Patient not found"})
    from django.utils import timezone
    today      = timezone.now().date()
    medicines  = Medicine.objects.filter(patient=patient, date=today)
    total      = medicines.count()
    taken      = medicines.filter(status='taken').count()
    missed     = medicines.filter(status='missed').count()
    pending    = medicines.filter(status='pending').count()
    compliance = f"{int((taken / total) * 100)}%" if total > 0 else "No medicines today"
    medicine_list = [
        {"name": m.name, "dosage": m.dosage or "N/A", "time": str(m.time), "status": m.status}
        for m in medicines
    ]
    return Response({
        "patient": patient.username, "date": str(today),
        "total_medicines": total, "taken": taken, "missed": missed,
        "pending": pending, "compliance": compliance, "today_medicines": medicine_list,
    })


# =================================================================
# API 2 — LOW STOCK ALERT
# =================================================================
@api_view(['POST'])
def low_stock_alert(request):
    patient_name       = request.data.get("patient_name")
    medicine_name      = request.data.get("medicine_name")
    quantity_remaining = request.data.get("quantity_remaining")
    if not (patient_name and medicine_name and quantity_remaining is not None):
        return Response({"error": "Missing data."})
    patient = User.objects.filter(username__iexact=patient_name.strip()).first()
    if not patient:
        return Response({"error": "Patient not found"})
    slot, _ = DispenserSlot.objects.get_or_create(
        patient=patient,
        medicine_name__iexact=medicine_name.strip(),
        defaults={'medicine_name': medicine_name.strip(), 'expected_medicine': medicine_name.strip(), 'quantity': quantity_remaining}
    )
    slot.quantity = int(quantity_remaining)
    slot.save()
    if slot.quantity == 0:
        alert_level, message = "CRITICAL", f"⛔ {medicine_name} is EMPTY! Refill immediately."
    elif slot.quantity <= 3:
        alert_level, message = "WARNING", f"⚠️ Only {slot.quantity} pills left. Refill soon."
    else:
        alert_level, message = "OK", f"✅ Stock OK. {slot.quantity} pills remaining."
    return Response({"patient": patient.username, "medicine": medicine_name,
                     "quantity_remaining": slot.quantity, "alert_level": alert_level, "message": message})


# =================================================================
# API 3 — WRONG MEDICINE
# =================================================================
@api_view(['POST'])
def wrong_medicine(request):
    patient_name = request.data.get("patient_name")
    expected     = request.data.get("expected")
    actual       = request.data.get("actual")
    if not (patient_name and expected and actual):
        return Response({"error": "Missing data."})
    patient = User.objects.filter(username__iexact=patient_name.strip()).first()
    if not patient:
        return Response({"error": "Patient not found"})
    slot = DispenserSlot.objects.filter(patient=patient, medicine_name__iexact=expected.strip()).first()
    if not slot:
        slot = DispenserSlot.objects.create(
            patient=patient, medicine_name=expected.strip(),
            expected_medicine=expected.strip(), actual_medicine=actual.strip(), quantity=0)
        return Response({"alert": "❌ WRONG MEDICINE DETECTED (new slot created)"})
    slot.actual_medicine = actual.strip()
    slot.save()
    alert   = "❌ WRONG MEDICINE" if slot.actual_medicine.lower() != slot.expected_medicine.lower() else "✅ Correct"
    message = f"Expected '{expected}' but got '{actual}'." if "❌" in alert else f"Medicine matches."
    return Response({"patient": patient.username, "expected": slot.expected_medicine,
                     "actual": slot.actual_medicine, "alert": alert, "message": message})


# ----------------- PROFILE VIEW -----------------
@login_required
def patient_profile_view(request, user_id):
    user            = get_object_or_404(User, id=user_id)
    profile         = user.profile
    medicines       = Medicine.objects.filter(patient=user).order_by('-id')
    return render(request, 'main/patient_profile.html', {
        'profile_user': user,
        'profile':      profile,
        'medicines':    medicines,
    })


# ----------------- EDIT PROFILE -----------------
@login_required
def edit_profile(request):
    profile = request.user.profile
    if request.method == 'POST':
        profile.age             = request.POST.get('age')
        profile.gender          = request.POST.get('gender')
        profile.phone           = request.POST.get('phone')
        profile.address         = request.POST.get('address')
        profile.medical_history = request.POST.get('medical_history')
        profile.save()
        return redirect('user_dashboard')
    return render(request, 'main/edit_profile.html', {'profile': profile})

# =====================================================================
# MOBILE APP JSON API  (used by the Flutter app — session-cookie based,
# no JWT needed for a capstone-scope project; DRF renders JSON for us)
# =====================================================================

@api_view(['POST'])
@authentication_classes([CsrfExemptSessionAuthentication])
def api_login(request):
    """POST {username, password} -> logs in (sets session cookie) + returns role."""
    username = request.data.get('username', '')
    password = request.data.get('password', '')
    user = authenticate(request, username=username, password=password)
    if user is None:
        return Response({'success': False, 'error': 'Invalid username or password'}, status=401)
    login(request, user)
    profile = get_user_role(user)
    return Response({
        'success': True,
        'username': user.username,
        'user_id': user.id,
        'role': profile.role,
    })


@api_view(['POST'])
@authentication_classes([CsrfExemptSessionAuthentication])
def api_signup(request):
    """POST {username, password, role} -> creates account, logs in, returns role.
    Role restricted to patient/caregiver — doctor accounts are created via the
    web dashboard by an admin, matching existing web signup behaviour."""
    username = request.data.get('username', '').strip()
    password = request.data.get('password', '')
    role = request.data.get('role', '').strip().lower()

    if not username or not password or not role:
        return Response({'error': 'username, password and role are all required'}, status=400)
    if role not in ('patient', 'caregiver'):
        return Response({'error': "role must be 'patient' or 'caregiver'"}, status=400)
    if len(password) < 4:
        return Response({'error': 'password must be at least 4 characters'}, status=400)
    if User.objects.filter(username=username).exists():
        return Response({'error': 'That username is already taken'}, status=400)

    user = User.objects.create_user(username=username, password=password)
    Profile.objects.create(user=user, role=role)
    login(request, user)

    return Response({
        'success': True,
        'username': user.username,
        'user_id': user.id,
        'role': role,
    })


@api_view(['POST'])
@authentication_classes([CsrfExemptSessionAuthentication])
def api_logout(request):
    logout(request)
    return Response({'success': True})


def _medicine_json(med):
    return {
        'id': med.id,
        'name': med.name,
        'dosage': med.dosage,
        'time': med.time.strftime('%H:%M'),
        'date': str(med.date),
        'status': med.status,
        'notes': med.notes,
        'patient_id': med.patient_id,
        'patient_username': med.patient.username,
    }


@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication])
def api_my_medicines(request):
    """Patient: their own medicines. Caregiver: all assigned patients' medicines."""
    if not request.user.is_authenticated:
        return Response({'error': 'Not authenticated'}, status=401)

    profile = get_user_role(request.user)

    if profile.role == 'patient':
        medicines = Medicine.objects.filter(patient=request.user).order_by('time')
    elif profile.role == 'caregiver':
        patients = User.objects.filter(profile__caregiver=request.user)
        medicines = Medicine.objects.filter(patient__in=patients).order_by('time')
    else:
        return Response({'error': 'Role not supported on mobile yet'}, status=403)

    return Response({'medicines': [_medicine_json(m) for m in medicines]})


@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication])
def api_caregiver_patients(request):
    if not request.user.is_authenticated:
        return Response({'error': 'Not authenticated'}, status=401)
    profile = get_user_role(request.user)
    if profile.role != 'caregiver':
        return Response({'error': 'Caregiver only'}, status=403)

    patients = User.objects.filter(profile__caregiver=request.user)
    data = [{
        'id': p.id,
        'username': p.username,
        'has_prescription': bool(p.profile.prescription_image),
    } for p in patients]
    return Response({'patients': data})


@api_view(['POST'])
@authentication_classes([CsrfExemptSessionAuthentication])
def api_take_medicine(request, med_id):
    if not request.user.is_authenticated:
        return Response({'error': 'Not authenticated'}, status=401)
    profile = get_user_role(request.user)
    med = get_object_or_404(Medicine, id=med_id)

    if profile.role == 'patient' and med.patient != request.user:
        return Response({'error': 'Forbidden'}, status=403)
    if profile.role == 'caregiver' and med.patient.profile.caregiver != request.user:
        return Response({'error': 'Forbidden'}, status=403)
    if profile.role not in ('patient', 'caregiver'):
        return Response({'error': 'Forbidden'}, status=403)

    med.status = 'taken'
    med.save()
    MedicineHistory.objects.create(medicine=med, action='taken')
    return Response({'success': True, 'medicine': _medicine_json(med)})


@api_view(['POST'])
@authentication_classes([CsrfExemptSessionAuthentication])
def api_mark_missed(request, med_id):
    if not request.user.is_authenticated:
        return Response({'error': 'Not authenticated'}, status=401)
    profile = get_user_role(request.user)
    med = get_object_or_404(Medicine, id=med_id)

    if profile.role == 'patient' and med.patient != request.user:
        return Response({'error': 'Forbidden'}, status=403)
    if profile.role == 'caregiver' and med.patient.profile.caregiver != request.user:
        return Response({'error': 'Forbidden'}, status=403)
    if profile.role not in ('patient', 'caregiver'):
        return Response({'error': 'Forbidden'}, status=403)

    med.status = 'missed'
    med.save()
    MedicineHistory.objects.create(medicine=med, action='missed')
    return Response({'success': True, 'medicine': _medicine_json(med)})


@api_view(['POST'])
@authentication_classes([CsrfExemptSessionAuthentication])
def api_refill_slot(request, slot_id):
    if not request.user.is_authenticated:
        return Response({'error': 'Not authenticated'}, status=401)
    profile = get_user_role(request.user)
    if profile.role != 'caregiver':
        return Response({'error': 'Caregiver only'}, status=403)

    slot = get_object_or_404(DispenserSlot, id=slot_id, patient__profile__caregiver=request.user)
    qty = request.data.get('quantity')
    if qty is None or not str(qty).isdigit():
        return Response({'error': 'quantity must be a non-negative integer'}, status=400)

    slot.quantity = int(qty)
    slot.save()
    return Response({'success': True, 'slot_id': slot.id, 'quantity': slot.quantity})


@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication])
def api_dispenser_slots(request):
    if not request.user.is_authenticated:
        return Response({'error': 'Not authenticated'}, status=401)
    profile = get_user_role(request.user)

    if profile.role == 'patient':
        slots = DispenserSlot.objects.filter(patient=request.user)
    elif profile.role == 'caregiver':
        patients = User.objects.filter(profile__caregiver=request.user)
        slots = DispenserSlot.objects.filter(patient__in=patients)
    else:
        return Response({'error': 'Role not supported'}, status=403)

    data = [{
        'id': s.id,
        'medicine_name': s.medicine_name,
        'quantity': s.quantity,
        'expected_medicine': s.expected_medicine,
        'actual_medicine': s.actual_medicine,
        'patient_id': s.patient_id,
    } for s in slots]
    return Response({'slots': data})


# ----------------- DUMMY AI / HARDWARE ENDPOINT (placeholder) -----------------
# The real PillScope (YOLOv8) model + ESP32 hardware aren't wired in yet.
# This returns a realistic fake response so the app can be built end-to-end now;
# swap the body of this view for the real inference call once hardware/model
# integration is ready — the response shape stays the same, so the app won't
# need any changes on that day.
import random

@api_view(['POST'])
@authentication_classes([CsrfExemptSessionAuthentication])
def api_dummy_pill_detection(request):
    """POST {medicine_name} -> fake YOLO-style detection + sensor confirmation."""
    expected_name = request.data.get('medicine_name', 'Unknown')
    confidence = round(random.uniform(0.85, 0.99), 4)
    ir_confirmed = True
    weight_grams = round(random.uniform(0.4, 1.2), 2)

    return Response({
        'source': 'dummy',  # flip to 'pillscope-yolov8' once real model is wired in
        'detected_medicine': expected_name,
        'confidence': confidence,
        'ir_break_beam_confirmed': ir_confirmed,
        'load_cell_weight_g': weight_grams,
        'verified': confidence > 0.90 and ir_confirmed,
    })


# =====================================================================
# MOBILE APP JSON API — Part 2: profile, caregiver, prescription, add medicine
# (feature parity with the web app, for the Flutter app)
# =====================================================================

def _profile_json(user, profile):
    return {
        'user_id': user.id,
        'username': user.username,
        'age': profile.age,
        'gender': profile.gender,
        'phone': profile.phone,
        'address': profile.address,
        'medical_history': profile.medical_history,
        'caregiver_id': profile.caregiver_id,
        'caregiver_username': profile.caregiver.username if profile.caregiver else None,
        'has_prescription': bool(profile.prescription_image),
        'prescription_url': profile.prescription_image.url if profile.prescription_image else None,
    }


@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication])
def api_my_profile(request):
    if not request.user.is_authenticated:
        return Response({'error': 'Not authenticated'}, status=401)
    profile = get_user_role(request.user)
    return Response(_profile_json(request.user, profile))


@api_view(['POST'])
@authentication_classes([CsrfExemptSessionAuthentication])
def api_update_profile(request):
    if not request.user.is_authenticated:
        return Response({'error': 'Not authenticated'}, status=401)
    profile = get_user_role(request.user)
    for field in ['age', 'gender', 'phone', 'address', 'medical_history']:
        if field in request.data:
            setattr(profile, field, request.data.get(field))
    profile.save()
    return Response({'success': True, 'profile': _profile_json(request.user, profile)})


@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication])
def api_available_caregivers(request):
    if not request.user.is_authenticated:
        return Response({'error': 'Not authenticated'}, status=401)
    profile = get_user_role(request.user)
    if profile.role != 'patient':
        return Response({'error': 'Patient only'}, status=403)
    caregivers = User.objects.filter(profile__role='caregiver')
    return Response({'caregivers': [{'id': c.id, 'username': c.username} for c in caregivers]})


@api_view(['POST'])
@authentication_classes([CsrfExemptSessionAuthentication])
def api_assign_caregiver(request):
    if not request.user.is_authenticated:
        return Response({'error': 'Not authenticated'}, status=401)
    profile = get_user_role(request.user)
    if profile.role != 'patient':
        return Response({'error': 'Patient only'}, status=403)
    caregiver_id = request.data.get('caregiver_id')
    if not caregiver_id:
        return Response({'error': 'caregiver_id required'}, status=400)
    caregiver_user = get_object_or_404(User, id=caregiver_id, profile__role='caregiver')
    profile.caregiver = caregiver_user
    profile.save()
    return Response({'success': True, 'caregiver_username': caregiver_user.username})


@api_view(['POST'])
@authentication_classes([CsrfExemptSessionAuthentication])
def api_upload_prescription(request):
    """multipart/form-data: image=<file>, patient_id=<optional, for caregiver>"""
    if not request.user.is_authenticated:
        return Response({'error': 'Not authenticated'}, status=401)
    profile = get_user_role(request.user)
    role = profile.role

    patient_id = request.data.get('patient_id')
    if role == 'patient':
        patient = request.user
    elif role == 'caregiver':
        if not patient_id:
            return Response({'error': 'patient_id required'}, status=400)
        patient = get_object_or_404(User, id=patient_id, profile__caregiver=request.user)
    else:
        return Response({'error': 'Forbidden'}, status=403)

    image = request.FILES.get('image')
    if not image:
        return Response({'error': 'No image provided'}, status=400)

    patient_profile = patient.profile
    patient_profile.prescription_image = image
    patient_profile.save()
    return Response({'success': True, 'prescription_url': patient_profile.prescription_image.url})


@api_view(['POST'])
@authentication_classes([CsrfExemptSessionAuthentication])
def api_delete_prescription(request):
    if not request.user.is_authenticated:
        return Response({'error': 'Not authenticated'}, status=401)
    profile = get_user_role(request.user)
    role = profile.role

    patient_id = request.data.get('patient_id')
    if role == 'patient':
        patient = request.user
    elif role == 'caregiver':
        if not patient_id:
            return Response({'error': 'patient_id required'}, status=400)
        patient = get_object_or_404(User, id=patient_id, profile__caregiver=request.user)
    else:
        return Response({'error': 'Forbidden'}, status=403)

    patient_profile = patient.profile
    patient_profile.prescription_image = None
    patient_profile.save()
    return Response({'success': True})


@api_view(['POST'])
@authentication_classes([CsrfExemptSessionAuthentication])
def api_add_medicine(request):
    """POST {name, dosage, time (HH:MM), notes, patient_id (optional, caregiver only)}"""
    if not request.user.is_authenticated:
        return Response({'error': 'Not authenticated'}, status=401)
    profile = get_user_role(request.user)
    role = profile.role

    patient_id = request.data.get('patient_id')
    if role == 'patient':
        patient = request.user
    elif role == 'caregiver':
        if not patient_id:
            return Response({'error': 'patient_id required'}, status=400)
        patient = get_object_or_404(User, id=patient_id, profile__caregiver=request.user)
    else:
        return Response({'error': 'Forbidden — use the web dashboard to prescribe as a doctor'}, status=403)

    name = (request.data.get('name') or '').strip()
    dosage = (request.data.get('dosage') or '').strip()
    time_str = (request.data.get('time') or '').strip()
    notes = (request.data.get('notes') or '').strip()

    if not name or not dosage or not time_str:
        return Response({'error': 'name, dosage and time are required'}, status=400)

    from datetime import datetime as dt
    try:
        parsed_time = dt.strptime(time_str, '%H:%M').time()
    except ValueError:
        return Response({'error': 'time must be in HH:MM format'}, status=400)

    med = Medicine.objects.create(
        patient=patient,
        name=name,
        dosage=dosage,
        time=parsed_time,
        notes=notes,
        prescribed_by=request.user,
        status='pending',
    )
    MedicineHistory.objects.create(medicine=med, action='pending')
    return Response({'success': True, 'medicine': _medicine_json(med)})


# =====================================================================
# PRESCRIPTION OCR (handwriting-assist, not auto-fill)
# =====================================================================
# Runs Tesseract OCR on the uploaded prescription image to produce a
# best-effort readable draft. This is NEVER auto-saved as the source of
# truth — a doctor or caregiver must review and confirm/correct it first
# (handwriting OCR is unreliable enough that skipping this step would be
# a real safety risk). Patients can view the confirmed text but cannot
# edit it themselves.

import pytesseract
import io
from PIL import Image, ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES = True  # tolerate slightly corrupt/incomplete uploads instead of crashing


def _get_patient_and_profile_for_prescription(request, patient_id=None):
    """Resolve which patient's prescription is being worked on, and check
    the requesting user is allowed to touch it (doctor, assigned caregiver,
    or the patient themself for read-only access)."""
    requester_profile = get_user_role(request.user)

    if patient_id:
        patient = get_object_or_404(User, id=patient_id)
    else:
        patient = request.user

    if requester_profile.role == 'patient' and patient != request.user:
        return None, None, Response({'error': 'Forbidden'}, status=403)
    if requester_profile.role == 'caregiver' and patient.profile.caregiver != request.user:
        return None, None, Response({'error': 'Forbidden'}, status=403)
    # doctors can access any patient's prescription (matches existing web behaviour)

    return patient, patient.profile, None


@api_view(['POST'])
@authentication_classes([CsrfExemptSessionAuthentication])
def api_run_prescription_ocr(request):
    """Run OCR on the patient's already-uploaded prescription image.
    Returns the raw extracted text — does NOT save anything yet.
    Doctor or caregiver only (matches who is allowed to confirm)."""
    if not request.user.is_authenticated:
        return Response({'error': 'Not authenticated'}, status=401)

    requester_profile = get_user_role(request.user)
    if requester_profile.role not in ('doctor', 'caregiver'):
        return Response({'error': 'Only a doctor or caregiver can run OCR'}, status=403)

    patient_id = request.data.get('patient_id')
    patient, profile, err = _get_patient_and_profile_for_prescription(request, patient_id)
    if err:
        return err

    if not profile.prescription_image:
        return Response({'error': 'No prescription image uploaded for this patient yet'}, status=400)

    try:
        img = Image.open(profile.prescription_image.path)
        img.load()  # force full decode now, with truncation tolerance enabled above
        img = img.convert('RGB')

        # Re-encode to a clean in-memory copy before OCR — Tesseract's own
        # JPEG decoder is stricter than PIL's and can crash on files that
        # PIL opens fine (e.g. slightly truncated phone/WhatsApp exports).
        clean_buffer = io.BytesIO()
        img.save(clean_buffer, format='PNG')
        clean_buffer.seek(0)
        clean_img = Image.open(clean_buffer)

        raw_text = pytesseract.image_to_string(clean_img).strip()
    except Exception as e:
        return Response({'error': f'OCR failed: {str(e)}'}, status=500)

    profile.prescription_ocr_text = raw_text
    profile.save()

    return Response({
        'success': True,
        'ocr_text': raw_text,
        'note': 'This is a best-effort machine reading of handwriting and may contain '
                'errors. Please review and correct it before confirming.',
    })


@api_view(['POST'])
@authentication_classes([CsrfExemptSessionAuthentication])
def api_confirm_prescription_text(request):
    """Save the doctor/caregiver-reviewed (and possibly corrected) readable
    version of the prescription. This becomes the trusted text shown to
    everyone, replacing the raw OCR guess."""
    if not request.user.is_authenticated:
        return Response({'error': 'Not authenticated'}, status=401)

    requester_profile = get_user_role(request.user)
    if requester_profile.role not in ('doctor', 'caregiver'):
        return Response({'error': 'Only a doctor or caregiver can confirm prescription text'}, status=403)

    patient_id = request.data.get('patient_id')
    confirmed_text = request.data.get('confirmed_text', '').strip()
    if not confirmed_text:
        return Response({'error': 'confirmed_text is required'}, status=400)

    patient, profile, err = _get_patient_and_profile_for_prescription(request, patient_id)
    if err:
        return err

    from django.utils import timezone
    profile.prescription_confirmed_text = confirmed_text
    profile.prescription_confirmed_by = request.user
    profile.prescription_confirmed_at = timezone.now()
    profile.save()

    return Response({
        'success': True,
        'confirmed_text': confirmed_text,
        'confirmed_by': request.user.username,
        'confirmed_at': profile.prescription_confirmed_at.isoformat(),
    })


@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication])
def api_get_prescription_text(request):
    """Read-only fetch of both the raw OCR guess and the confirmed text
    (if any) for a patient's prescription. Available to patient (own),
    caregiver (assigned), and doctor (any)."""
    if not request.user.is_authenticated:
        return Response({'error': 'Not authenticated'}, status=401)

    patient_id = request.GET.get('patient_id')
    patient, profile, err = _get_patient_and_profile_for_prescription(request, patient_id)
    if err:
        return err

    return Response({
        'ocr_text': profile.prescription_ocr_text,
        'confirmed_text': profile.prescription_confirmed_text,
        'confirmed_by': profile.prescription_confirmed_by.username if profile.prescription_confirmed_by else None,
        'confirmed_at': profile.prescription_confirmed_at.isoformat() if profile.prescription_confirmed_at else None,
    })
