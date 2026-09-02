from django.urls import path
from . import views

urlpatterns = [
    # Home / Auth
    path('', views.redirect_user, name='home'),
    path('login/', views.login_view, name='login'),
    path('signup/', views.signup_view, name='signup'),
    path('logout/', views.logout_view, name='logout'),

    # Doctor
    path('doctor/', views.doctor_dashboard, name='doctor_dashboard'),
    path('doctor/patient/<int:patient_id>/', views.patient_detail, name='patient_detail'),
    path('doctor/patient/<int:patient_id>/add_medicine/', views.add_medicine, name='add_medicine'),

    # Patient
    path('patient/', views.user_dashboard, name='user_dashboard'),
    path('take/<int:med_id>/', views.take_medicine, name='take_medicine'),
    path('missed/<int:med_id>/', views.mark_missed, name='mark_missed'),
    path('patient/add_medicine/', views.add_medicine, name='patient_add_medicine'),

    # Caregiver
    path('caregiver/', views.caregiver_dashboard, name='caregiver_dashboard'),
    path('caregiver/patient/<int:patient_id>/add_medicine/', views.add_medicine, name='caregiver_add_medicine'),

    # Medicine History
    path('history/', views.medicine_history, name='medicine_history'),
    path('history/<int:patient_id>/', views.medicine_history, name='medicine_history_patient'),

    # (duplicate kept as requested)
    path('doctor/patient/<int:patient_id>/', views.patient_detail, name='patient_detail'),

    path('dispenser/', views.dispenser_status, name='dispenser_status'),
    path('dispenser/refill/<int:slot_id>/', views.refill_slot, name='refill_slot'),

    # ✅ PRESCRIPTION IMAGE — upload & delete (separate from add medicine)
    path('prescription/upload/', views.upload_prescription, name='upload_prescription'),
    path('prescription/upload/<int:patient_id>/', views.upload_prescription, name='upload_prescription_for'),
    path('prescription/delete/', views.delete_prescription, name='delete_prescription'),
    path('prescription/delete/<int:patient_id>/', views.delete_prescription, name='delete_prescription_for'),

    # APIs
    path('api/pill-event/', views.pill_event),
    path('dashboard/', views.dashboard),
    path('api/patient-status/', views.patient_status),
    path('api/low-stock/', views.low_stock_alert),
    path('api/wrong-medicine/', views.wrong_medicine),

    # Mobile app JSON APIs
    path('api/login/', views.api_login, name='api_login'),
    path('api/signup/', views.api_signup, name='api_signup'),
    path('api/logout/', views.api_logout, name='api_logout'),
    path('api/my-medicines/', views.api_my_medicines, name='api_my_medicines'),
    path('api/caregiver/patients/', views.api_caregiver_patients, name='api_caregiver_patients'),
    path('api/take/<int:med_id>/', views.api_take_medicine, name='api_take_medicine'),
    path('api/missed/<int:med_id>/', views.api_mark_missed, name='api_mark_missed'),
    path('api/dispenser-slots/', views.api_dispenser_slots, name='api_dispenser_slots'),
    path('api/dispenser/refill/<int:slot_id>/', views.api_refill_slot, name='api_refill_slot'),
    path('api/dummy-pill-detection/', views.api_dummy_pill_detection, name='api_dummy_pill_detection'),

    path('api/profile/', views.api_my_profile, name='api_my_profile'),
    path('api/profile/update/', views.api_update_profile, name='api_update_profile'),
    path('api/caregivers/', views.api_available_caregivers, name='api_available_caregivers'),
    path('api/assign-caregiver/', views.api_assign_caregiver, name='api_assign_caregiver'),
    path('api/prescription/upload/', views.api_upload_prescription, name='api_upload_prescription'),
    path('api/prescription/delete/', views.api_delete_prescription, name='api_delete_prescription'),
    path('api/add-medicine/', views.api_add_medicine, name='api_add_medicine'),
    path('api/prescription/ocr/', views.api_run_prescription_ocr, name='api_run_prescription_ocr'),
    path('api/prescription/confirm-text/', views.api_confirm_prescription_text, name='api_confirm_prescription_text'),
    path('api/prescription/text/', views.api_get_prescription_text, name='api_get_prescription_text'),

    # Profile
    path('profile/<int:user_id>/', views.patient_profile_view, name='patient_profile'),
    path('edit-profile/', views.edit_profile, name='edit_profile'),
]