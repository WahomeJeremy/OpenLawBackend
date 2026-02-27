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
                # Handle empty year_filed values
                year_filed = row.get('year_filed', '').strip()
                year_filed = int(year_filed) if year_filed and year_filed.isdigit() else None
                
                # Generate case number from case title or use a default
                case_title = row.get('case_title', '').strip()
                case_number = case_title.split('[')[-1].split(']')[0] if '[' in case_title and ']' in case_title else f"ELC-{count+1}"
                
                Case.objects.update_or_create(
                    case_number=case_number,
                    defaults={
                        'case_name': case_title,
                        'year': year_filed,
                        'court': row.get('court_station', '').strip(),
                        'plaintiff': row.get('plaintiff', '').strip(),
                        'defendant': row.get('defendant', '').strip(),
                        'status': row.get('judgment_type', '').strip(),
                        'summary': row.get('land_references', '').strip(),
                        'parties': f"{row.get('plaintiff', '').strip()} vs {row.get('defendant', '').strip()}"
                    }
                )
                count += 1
                
                if count % 100 == 0:
                    self.stdout.write(f'Imported {count} cases...')
        
        self.stdout.write(self.style.SUCCESS(f'Successfully imported {count} cases from CSV'))
