#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
import django

def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pill_dispenser.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)

if __name__ == '__main__':
    main()  # this runs Django commands

    # --- Post-run database script (optional, outside normal manage.py workflow) ---
    # Initialize Django manually
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pill_dispenser.settings')
    django.setup()

    from main.models import Medicine
    from django.contrib.auth.models import User

    # Ensure all medicines have a corresponding user
    for med in Medicine.objects.all():
        if not User.objects.filter(id=med.patient_id).exists():
            # Create a dummy user for missing patient
            dummy_user = User.objects.create(username=f'dummy{med.patient_id}')
            print(f"Created dummy user for patient_id {med.patient_id}")