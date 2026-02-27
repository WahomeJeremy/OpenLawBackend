from django.core.management.base import BaseCommand
from cases.models import Case

class Command(BaseCommand):
    help = 'Check imported case data'

    def handle(self, *args, **options):
        total_cases = Case.objects.count()
        self.stdout.write(f'Total cases: {total_cases}')
        
        self.stdout.write('\nSample cases:')
        for case in Case.objects.all()[:10]:
            self.stdout.write(f'{case.case_number}: {case.case_name[:80]}...')
            self.stdout.write(f'  Plaintiff: {case.plaintiff}')
            self.stdout.write(f'  Defendant: {case.defendant}')
            self.stdout.write(f'  Year: {case.year}')
            self.stdout.write('---')

        self.stdout.write('\nSearching for cases with "ELC" in case_number:')
        elc_cases = Case.objects.filter(case_number__icontains='elc')
        self.stdout.write(f'Found {elc_cases.count()} cases')
        for case in elc_cases[:5]:
            self.stdout.write(f'{case.case_number}: {case.case_name[:50]}...')

        self.stdout.write('\nSearching for cases with "157" in case_number:')
        cases_157 = Case.objects.filter(case_number__icontains='157')
        self.stdout.write(f'Found {cases_157.count()} cases')
        for case in cases_157:
            self.stdout.write(f'{case.case_number}: {case.case_name[:50]}...')
