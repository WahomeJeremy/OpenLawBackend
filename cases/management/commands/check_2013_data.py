from django.core.management.base import BaseCommand
from cases.models import Case

class Command(BaseCommand):
    help = 'Check 2013 case data specifically'

    def handle(self, *args, **options):
        # Check cases that should have numeric case numbers from 2013
        numeric_cases = Case.objects.filter(year=2013).order_by('case_number')[:10]
        
        self.stdout.write('2013 Cases (should be numeric case_id values):')
        for case in numeric_cases:
            self.stdout.write(f'{case.case_number}: {case.case_name[:50]}...')
            self.stdout.write(f'  Year: {case.year}')
            self.stdout.write('---')
        
        # Also check for any cases with case_number that contains only digits
        digit_cases = Case.objects.filter(case_number__regex=r'^\d+$')
        self.stdout.write(f'\nCases with pure numeric case numbers: {digit_cases.count()}')
        for case in digit_cases[:5]:
            self.stdout.write(f'{case.case_number}: {case.case_name[:50]}...')
