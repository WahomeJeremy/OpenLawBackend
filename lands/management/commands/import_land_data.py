import csv
import os
import re
from django.core.management.base import BaseCommand
from django.conf import settings
from lands.models import Land
from cases.models import Case

class Command(BaseCommand):
    help = 'Import land data from CSV files'

    def handle(self, *args, **options):
        # Import from 2013 CSV
        csv_2013_path = os.path.join(settings.BASE_DIR, 'Kenya_ELC_2013_clean.csv')
        if os.path.exists(csv_2013_path):
            self.import_from_csv(csv_2013_path, "2013")
        
        # Import from 2019 CSV
        csv_2019_path = os.path.join(settings.BASE_DIR, 'Kenya_ELC_2019.csv')
        if os.path.exists(csv_2019_path):
            self.import_from_csv(csv_2019_path, "2019")
        
        self.stdout.write(self.style.SUCCESS('Land data import completed'))

    def import_from_csv(self, csv_file_path, year):
        self.stdout.write(f'Importing land data from {csv_file_path}')
        
        with open(csv_file_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            count = 0
            
            for row in reader:
                land_references = row.get('land_references', '').strip()
                if not land_references:
                    continue
                
                # Extract land references from text
                land_refs = self.extract_land_references(land_references)
                
                for land_ref in land_refs:
                    # Clean and truncate land reference to fit in database
                    cleaned_ref = land_ref.strip()[:250]  # Truncate to 250 chars to be safe
                    
                    if not cleaned_ref:
                        continue
                    
                    # Create or update land record
                    land, created = Land.objects.update_or_create(
                        title_number=cleaned_ref,
                        defaults={
                            'lr_number': self.extract_lr_number(cleaned_ref)[:250],
                            'plot_number': self.extract_plot_number(cleaned_ref)[:250],
                            'county': self.extract_county(row)[:100]
                        }
                    )
                    
                    # Link to case if case exists
                    case_title = row.get('case_title', '').strip()
                    if case_title:
                        try:
                            case = Case.objects.filter(case_name__icontains=case_title.split('[')[0].strip()).first()
                            if case:
                                land.cases.add(case)
                        except:
                            pass
                    
                    if created:
                        count += 1
                
                if count % 10 == 0 and count > 0:
                    self.stdout.write(f'Imported {count} land records from {year} data...')
        
        self.stdout.write(self.style.SUCCESS(f'Imported {count} land records from {year} CSV'))

    def extract_land_references(self, text):
        """Extract land references from text"""
        if not text:
            return []
        
        # Common patterns for land references - updated to match actual data
        patterns = [
            r'L\.?\s*R\.?\s*NO\.?\s*([A-Z0-9/\-\s]+)',  # L.R. NO. 776/4/2
            r'L\.?\s*R\.?\s*([A-Z0-9/\-\s]+)',          # L. R. No. KIIRUA/272
            r'LR\s*NO\.?\s*([A-Z0-9/\-\s]+)',          # LR NO. 776/4/2
            r'LR\s*([A-Z0-9/\-\s]+)',                  # LR 776/4/2
            r'([A-Z0-9]+/[A-Z0-9]+)',                  # 776/4/2
            r'([A-Z]+\s+[A-Z0-9/\-]+)',               # KISUMU MUNICIPALITY/BLOCK 9/1
            r'Block\s+([0-9]+/[0-9]+)',                # Block 9/1
            r'MUNICIPALITY/BLOCK\s+([0-9]+/[0-9]+)',   # MUNICIPALITY/BLOCK 9/1
        ]
        
        land_refs = set()
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                # Clean up the match
                cleaned = match.strip()
                # Remove extra spaces and normalize
                cleaned = re.sub(r'\s+', ' ', cleaned)
                cleaned = cleaned.strip()
                
                # Filter out very short matches and common words
                if len(cleaned) > 2 and not cleaned.lower() in ['no', 'block', 'municipality']:
                    land_refs.add(cleaned)
        
        return list(land_refs)

    def extract_lr_number(self, land_ref):
        """Extract LR number from land reference"""
        if 'LR' in land_ref.upper() or 'L.R' in land_ref:
            return land_ref
        return f"LR {land_ref}"

    def extract_plot_number(self, land_ref):
        """Extract plot number from land reference"""
        if 'Plot' in land_ref:
            return land_ref
        return f"Plot {land_ref}"

    def extract_location(self, row):
        """Extract location from court station or other data"""
        court = row.get('court_station', '').strip() or row.get('court', '').strip()
        if court:
            # Extract city name from court
            if 'NAIROBI' in court.upper():
                return 'Nairobi'
            elif 'MOMBASA' in court.upper():
                return 'Mombasa'
            elif 'KISUMU' in court.upper():
                return 'Kisumu'
            elif 'NAKURU' in court.upper():
                return 'Nakuru'
            elif 'ELDORET' in court.upper():
                return 'Eldoret'
        return 'Unknown'

    def extract_county(self, row):
        """Extract county from location data"""
        location = self.extract_location(row)
        if location != 'Unknown':
            return location
        return 'Unknown'
