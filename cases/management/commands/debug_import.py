import csv
import os
from django.core.management.base import BaseCommand
from django.conf import settings

class Command(BaseCommand):
    help = 'Debug CSV import to see exact values'

    def handle(self, *args, **options):
        csv_file_path = os.path.join(settings.BASE_DIR, 'Kenya_ELC_2013_clean.csv')
        
        with open(csv_file_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            
            self.stdout.write('First 5 rows from 2013 CSV:')
            for i, row in enumerate(reader):
                if i >= 5:
                    break
                    
                self.stdout.write(f'Row {i+1}:')
                self.stdout.write(f'  case_id: "{row.get("case_id", "")}"')
                self.stdout.write(f'  plaintiff: "{row.get("plaintiff", "")}"')
                self.stdout.write(f'  defendant: "{row.get("defendant", "")}"')
                self.stdout.write(f'  case_title: "{row.get("case_title", "")}"')
                self.stdout.write('---')
