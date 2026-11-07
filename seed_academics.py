"""
Seed script: Creates initial Academic Structure data for Majang Secondary School.
Run with: python manage.py shell < seed_academics.py
Or:        python seed_academics.py  (with DJANGO_SETTINGS_MODULE set)
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from datetime import date
from academics.models import AcademicYear, Grade, Section, Stream, Subject

print("=" * 55)
print("  SSMS Academic Structure Seed Script")
print("=" * 55)

# ---------- Academic Year ----------
ay, created = AcademicYear.objects.get_or_create(
    code='AY-2026',
    defaults={
        'name': '2026/2027 Academic Year (2018/2019 E.C.)',
        'start_date': date(2026, 9, 11),
        'end_date': date(2027, 7, 8),
        'is_current': True,
        'is_closed': False,
    }
)
if created:
    AcademicYear.objects.filter(is_current=True).exclude(pk=ay.pk).update(is_current=False)
    ay.is_current = True
    ay.save(update_fields=['is_current'])
    print(f"[CREATED] Academic Year: {ay.name}")
else:
    print(f"[EXISTS]  Academic Year: {ay.name}")

# ---------- Grades ----------
grades_data = [
    ('Grade 9',  9),
    ('Grade 10', 10),
    ('Grade 11', 11),
    ('Grade 12', 12),
]
for gname, level in grades_data:
    g, created = Grade.objects.get_or_create(
        level=level,
        defaults={'name': gname, 'is_active': True}
    )
    tag = "CREATED" if created else "EXISTS "
    print(f"[{tag}] Grade: {gname}")

# ---------- Sections ----------
for sec_name in ['A', 'B', 'C']:
    s, created = Section.objects.get_or_create(
        name=sec_name,
        defaults={'is_active': True}
    )
    tag = "CREATED" if created else "EXISTS "
    print(f"[{tag}] Section: {sec_name}")

# ---------- Streams ----------
streams_data = [
    ('NATURAL', 'Natural Science'),
    ('SOCIAL',  'Social Science'),
]
for code, name in streams_data:
    st, created = Stream.objects.get_or_create(
        code=code,
        defaults={'name': name, 'is_active': True}
    )
    tag = "CREATED" if created else "EXISTS "
    print(f"[{tag}] Stream: {name}")

# ---------- Subjects (Ethiopian Secondary Core) ----------
subjects_data = [
    ('ENG-09',   'English Language'),
    ('MATH-09',  'Mathematics'),
    ('PHYS-09',  'Physics'),
    ('CHEM-09',  'Chemistry'),
    ('BIO-09',   'Biology'),
    ('HIST-09',  'History'),
    ('GEO-09',   'Geography'),
    ('CIVICS',   'Civics and Ethical Education'),
    ('ICT-09',   'Information Technology'),
    ('PHYS-ED',  'Physical Education'),
    ('AMHARIC',  'Amharic Language'),
    ('ARTS-09',  'Arts Education'),
    ('ECON-09',  'Economics'),
    ('TECH-09',  'Technical Drawing'),
]
for code, name in subjects_data:
    subj, created = Subject.objects.get_or_create(
        code=code,
        defaults={'name': name, 'is_active': True}
    )
    tag = "CREATED" if created else "EXISTS "
    print(f"[{tag}] Subject: {name}")

print()
print("=" * 55)
print(f"  Academic Years : {AcademicYear.objects.count()}")
print(f"  Grades         : {Grade.objects.count()}")
print(f"  Sections       : {Section.objects.count()}")
print(f"  Streams        : {Stream.objects.count()}")
print(f"  Subjects       : {Subject.objects.count()}")
print("=" * 55)
print("Seed complete. You can now use the Academic Management system.")
