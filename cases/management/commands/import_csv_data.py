import csv
import os
from django.core.management.base import BaseCommand
from django.conf import settings
from cases.models import Case

class Command(BaseCommand):
    help = 'Import case data from CSV file'

    def handle(self, *args, **options):
        csv_file_path = os.path.join(settings.BASE_DIR, 'Kenya_ELC_2019.csv')
        
        if not os.path.exists(csv_file_path):
            self.stdout.write(self.style.ERROR(f'CSV file not found at {csv_file_path}'))
            return

        with open(csv_file_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            count = 0
            
            for row in reader:
                Case.objects.update_or_create(
                    case_title=row['case_title'],
                    defaults={
                        'year_filed': int(row['year_filed']) if row['year_filed'] else None,
                        'court_station': row['court_station'],
                        'plaintiff': row['plaintiff'],
                        'defendant': row['defendant'],
                        'judgment_type': row['judgment_type'],
                        'land_references': row['land_references'],
                        'url': row['url']
                    }
                )
                count += 1
                
                if count % 100 == 0:
                    self.stdout.write(f'Imported {count} cases...')
        
        self.stdout.write(self.style.SUCCESS(f'Successfully imported {count} cases from CSV'))
