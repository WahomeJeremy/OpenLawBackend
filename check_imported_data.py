#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from cases.models import Case

print(f'Total cases: {Case.objects.count()}')
print('\nSample cases:')
for case in Case.objects.all()[:10]:
    print(f'{case.case_number}: {case.case_name[:80]}...')
    print(f'  Plaintiff: {case.plaintiff}')
    print(f'  Defendant: {case.defendant}')
    print(f'  Year: {case.year}')
    print('---')

print('\nSearching for cases with "ELC" in case_number:')
elc_cases = Case.objects.filter(case_number__icontains='elc')
print(f'Found {elc_cases.count()} cases')
for case in elc_cases[:5]:
    print(f'{case.case_number}: {case.case_name[:50]}...')

print('\nSearching for cases with "157" in case_number:')
cases_157 = Case.objects.filter(case_number__icontains='157')
print(f'Found {cases_157.count()} cases')
for case in cases_157:
    print(f'{case.case_number}: {case.case_name[:50]}...')
