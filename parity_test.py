import django, os, json, io
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pill_dispenser.settings')
django.setup()
from django.conf import settings
settings.ALLOWED_HOSTS = ['*']

from django.contrib.auth.models import User
from main.models import Profile, Medicine
from django.test import Client
from PIL import Image

errors = []
def check(label, resp, expect=(200,)):
    ok = resp.status_code in expect
    print(f"{'OK ' if ok else 'FAIL'} {label} -> {resp.status_code}")
    if not ok:
        errors.append((label, resp.status_code, resp.content.decode('utf-8', errors='replace')[:1500]))
    return resp

# ---- setup ----
cg, _ = User.objects.get_or_create(username='parity_cg'); cg.set_password('pass1234'); cg.save()
Profile.objects.get_or_create(user=cg, defaults={'role': 'caregiver'})

pat, _ = User.objects.get_or_create(username='parity_pat'); pat.set_password('pass1234'); pat.save()
pprof, _ = Profile.objects.get_or_create(user=pat, defaults={'role': 'patient'})

pat2, _ = User.objects.get_or_create(username='parity_pat_unrelated'); pat2.set_password('pass1234'); pat2.save()
Profile.objects.get_or_create(user=pat2, defaults={'role': 'patient'})

c = Client(enforce_csrf_checks=True)
c.post('/api/login/', json.dumps({'username':'parity_pat','password':'pass1234'}), content_type='application/json')

# 1. get profile
resp = check("GET /api/profile/", c.get('/api/profile/'))
print("   ->", resp.json())

# 2. update profile
resp = check("POST /api/profile/update/", c.post('/api/profile/update/', json.dumps({
    'age': '34', 'gender': 'Female', 'phone': '9999999999', 'address': 'Bengaluru', 'medical_history': 'None'
}), content_type='application/json'))
print("   ->", resp.json())

# 3. available caregivers
resp = check("GET /api/caregivers/", c.get('/api/caregivers/'))
print("   -> caregivers:", resp.json())

# 4. assign caregiver
resp = check("POST /api/assign-caregiver/", c.post('/api/assign-caregiver/', json.dumps({'caregiver_id': cg.id}), content_type='application/json'))
print("   ->", resp.json())
pprof.refresh_from_db()
assert pprof.caregiver_id == cg.id, "caregiver not actually assigned!"

# 5. add medicine (patient, self)
resp = check("POST /api/add-medicine/ (patient)", c.post('/api/add-medicine/', json.dumps({
    'name': 'Vitamin D', 'dosage': '1 tab', 'time': '08:00', 'notes': 'with food'
}), content_type='application/json'))
print("   ->", resp.json())

# 6. upload prescription (multipart)
img = io.BytesIO(); Image.new('RGB', (10, 10)).save(img, format='JPEG'); img.seek(0)
resp = check("POST /api/prescription/upload/ (patient)", c.post('/api/prescription/upload/', {'image': img}))
print("   ->", resp.json())

# 7. profile now shows prescription
resp = c.get('/api/profile/')
print("   -> has_prescription after upload:", resp.json()['has_prescription'])
assert resp.json()['has_prescription'] == True

# 8. delete prescription
resp = check("POST /api/prescription/delete/", c.post('/api/prescription/delete/'))
resp2 = c.get('/api/profile/')
print("   -> has_prescription after delete:", resp2.json()['has_prescription'])
assert resp2.json()['has_prescription'] == False

# ============ CAREGIVER SIDE ============
c2 = Client(enforce_csrf_checks=True)
c2.post('/api/login/', json.dumps({'username':'parity_cg','password':'pass1234'}), content_type='application/json')

# 9. caregiver adds medicine for assigned patient
resp = check("POST /api/add-medicine/ (caregiver, assigned patient)", c2.post('/api/add-medicine/', json.dumps({
    'name': 'Metformin', 'dosage': '500mg', 'time': '20:00', 'patient_id': pat.id
}), content_type='application/json'))
print("   ->", resp.json())

# 10. SECURITY: caregiver tries to add medicine for UNASSIGNED patient -> must fail
resp = c2.post('/api/add-medicine/', json.dumps({
    'name': 'Hack', 'dosage': '1', 'time': '10:00', 'patient_id': pat2.id
}), content_type='application/json')
print(f"SECURITY CHECK: caregiver adding med for unrelated patient -> {resp.status_code} (expect 404)")
if resp.status_code == 200:
    errors.append(("SECURITY BUG: caregiver added medicine for unrelated patient", resp.status_code, resp.content.decode()))

# 11. caregiver uploads prescription for assigned patient
img2 = io.BytesIO(); Image.new('RGB', (10, 10)).save(img2, format='JPEG'); img2.seek(0)
resp = check("POST /api/prescription/upload/ (caregiver, for patient)", c2.post('/api/prescription/upload/', {'image': img2, 'patient_id': str(pat.id)}))
print("   ->", resp.json())

# 12. SECURITY: caregiver uploads prescription for UNASSIGNED patient -> must fail
img3 = io.BytesIO(); Image.new('RGB', (10, 10)).save(img3, format='JPEG'); img3.seek(0)
resp = c2.post('/api/prescription/upload/', {'image': img3, 'patient_id': str(pat2.id)})
print(f"SECURITY CHECK: caregiver uploading rx for unrelated patient -> {resp.status_code} (expect 404)")
if resp.status_code == 200:
    errors.append(("SECURITY BUG: caregiver uploaded prescription for unrelated patient", resp.status_code, resp.content.decode()))

# 13. patient tries to assign caregiver that doesn't exist -> should 404, not crash
resp = c.post('/api/assign-caregiver/', json.dumps({'caregiver_id': 99999}), content_type='application/json')
print(f"EDGE CASE: assign nonexistent caregiver -> {resp.status_code} (expect 404, not 500)")
if resp.status_code == 500:
    errors.append(("BUG: 500 error on invalid caregiver_id", resp.status_code, resp.content.decode()[:500]))

print("\n=== SUMMARY ===")
if errors:
    for label, code, content in errors:
        print(f"\n--- {label} ({code}) ---")
        print(content)
else:
    print("ALL PASSED, NO ERRORS")
