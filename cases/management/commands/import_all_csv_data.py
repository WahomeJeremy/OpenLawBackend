import csv
import os
import re
from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import transaction
from cases.models import Case
from lands.models import Land


class Command(BaseCommand):
    help = 'Import ALL case data from both Kenya_ELC_2013_clean.csv and Kenya_ELC_2019.csv files'

    def handle(self, *args, **options):
        total_imported = 0
        
        # Import 2013 data
        imported_2013 = self.import_2013_data()
        total_imported += imported_2013
        self.stdout.write(self.style.SUCCESS(f'Imported {imported_2013} cases from 2013 CSV'))
        
        # Import 2019 data
        imported_2019 = self.import_2019_data()
        total_imported += imported_2019
        self.stdout.write(self.style.SUCCESS(f'Imported {imported_2019} cases from 2019 CSV'))
        
        self.stdout.write(self.style.SUCCESS(f'Total cases imported: {total_imported}'))

    def import_2013_data(self):
        """Import data from Kenya_ELC_2013_clean.csv"""
        csv_file_path = os.path.join(settings.BASE_DIR, 'Kenya_ELC_2013_clean.csv')
        
        if not os.path.exists(csv_file_path):
            self.stdout.write(self.style.ERROR(f'2013 CSV file not found at {csv_file_path}'))
            return 0

        return self._process_csv_file(csv_file_path, '2013')

    def import_2019_data(self):
        """Import data from Kenya_ELC_2019.csv"""
        csv_file_path = os.path.join(settings.BASE_DIR, 'Kenya_ELC_2019.csv')
        
        if not os.path.exists(csv_file_path):
            self.stdout.write(self.style.ERROR(f'2019 CSV file not found at {csv_file_path}'))
            return 0

        return self._process_csv_file(csv_file_path, '2019')

    def _process_csv_file(self, csv_file_path, year_label):
        """Process a CSV file and import all records"""
        count = 0
        
        with open(csv_file_path, 'r', encoding='utf-8', errors='ignore') as file:
            reader = csv.DictReader(file)
            
            with transaction.atomic():
                for row in reader:
                    try:
                        # Extract case data based on CSV format
                        case_data, land_references = self._extract_case_data(row, year_label)
                        
                        # Create or update the case
                        case, created = Case.objects.update_or_create(
                            case_number=case_data['case_number'],
                            defaults=case_data
                        )
                        
                        # Process land references if they exist
                        if land_references:
                            self._process_land_references(case, land_references)
                        
                        count += 1
                        
                        if count % 100 == 0:
                            self.stdout.write(f'Processed {count} cases from {year_label} CSV...')
                            
                    except Exception as e:
                        self.stdout.write(self.style.WARNING(f'Error processing row {count + 1}: {str(e)}'))
                        continue
        
        return count

    def _extract_case_data(self, row, year_label):
        """Extract case data from CSV row based on year format"""
        
        if year_label == '2013':
            # 2013 CSV format: case_id,plaintiff,defendant,court,year_filed,land_references,case_title,url
            case_id = row.get('case_id', '').strip()
            plaintiff = row.get('plaintiff', '').strip()
            defendant = row.get('defendant', '').strip()
            court = row.get('court', '').strip()
            year_filed = row.get('year_filed', '').strip()
            land_references = row.get('land_references', '').strip()
            case_title = row.get('case_title', '').strip()
            url = row.get('url', '').strip()
            
            # Use case_id directly as case_number to preserve original format
            case_number = case_id if case_id else self._extract_case_number_from_title(case_title)
            
        else:
            # 2019 CSV format: year_filed,court_station,plaintiff,defendant,case_title,judgment_type,land_references,url
            year_filed = row.get('year_filed', '').strip()
            court_station = row.get('court_station', '').strip()
            plaintiff = row.get('plaintiff', '').strip()
            defendant = row.get('defendant', '').strip()
            case_title = row.get('case_title', '').strip()
            judgment_type = row.get('judgment_type', '').strip()
            land_references = row.get('land_references', '').strip()
            url = row.get('url', '').strip()
            
            # Extract case number from case_title for 2019 data
            case_number = self._extract_case_number_from_title(case_title)
            court = court_station
        
        # Handle year filed
        year = None
        if year_filed and year_filed.isdigit():
            year = int(year_filed)
        
        # Create parties string
        parties = f"{plaintiff} vs {defendant}" if plaintiff and defendant else case_title
        
        case_data = {
            'case_number': case_number,
            'case_name': case_title,
            'year': year,
            'court': court,
            'plaintiff': plaintiff if plaintiff else None,
            'defendant': defendant if defendant else None,
            'status': judgment_type if year_label == '2019' else 'Judgment',
            'summary': land_references if land_references else None,
            'parties': parties
        }
        
        return case_data, land_references

    def _extract_case_number_from_title(self, case_title):
        """Extract case number from case title"""
        if not case_title:
            return f"ELC-UNKNOWN-{hash(case_title) % 10000}"
        
        # Look for pattern like [2013] KEELC 157 or [2019] KEELC 1
        match = re.search(r'\[?\d{4}\]?\s*KEELC\s*(\d+)', case_title)
        if match:
            return f"KEELC-{match.group(1)}"
        
        # Alternative pattern: just numbers in brackets
        match = re.search(r'\[(\d+)\]', case_title)
        if match:
            return f"ELC-{match.group(1)}"
        
        # Fallback: use hash of title
        return f"ELC-{abs(hash(case_title)) % 10000}"

    def _process_land_references(self, case, land_references):
        """Process land references and create/update land records"""
        if not land_references or land_references.strip() == '':
            return
        
        # Split land references by common separators
        land_refs = re.split(r'[,;]\s*|\s+and\s+|\s+or\s+', land_references)
        
        for land_ref in land_refs:
            land_ref = land_ref.strip()
            if not land_ref:
                continue
            
            # Extract different types of land references
            land_data = self._parse_land_reference(land_ref)
            
            if land_data:
                # Create or update land record
                land, created = Land.objects.update_or_create(
                    title_number=land_data['title_number'],
                    defaults=land_data
                )
                
                # Associate land with case
                case.lands.add(land)

    def _parse_land_reference(self, land_ref):
        """Parse individual land reference to extract structured data"""
        land_ref = land_ref.strip()
        
        # Initialize with title number
        land_data = {
            'title_number': land_ref[:255],  # Truncate if too long
            'lr_number': None,
            'plot_number': None,
            'certificate_number': None,
            'allotment_number': None,
            'county': None
        }
        
        # Extract LR number
        lr_match = re.search(r'L\.?R\.?\s*No\.?\s*([A-Z0-9/\-]+)', land_ref, re.IGNORECASE)
        if lr_match:
            land_data['lr_number'] = lr_match.group(1)
        
        # Extract plot number
        plot_match = re.search(r'Plot\s+No\.?\s*([A-Z0-9/\-]+)', land_ref, re.IGNORECASE)
        if plot_match:
            land_data['plot_number'] = plot_match.group(1)
        
        # Extract certificate number
        cert_match = re.search(r'Certificate\s+No\.?\s*([A-Z0-9/\-]+)', land_ref, re.IGNORECASE)
        if cert_match:
            land_data['certificate_number'] = cert_match.group(1)
        
        # Extract allotment number
        allot_match = re.search(r'Allotment\s+No\.?\s*([A-Z0-9/\-]+)', land_ref, re.IGNORECASE)
        if allot_match:
            land_data['allotment_number'] = allot_match.group(1)
        
        # Extract county (common Kenyan counties)
        counties = [
            'Nairobi', 'Mombasa', 'Kisumu', 'Nakuru', 'Eldoret', 'Thika', 'Kitale',
            'Garissa', 'Kakuma', 'Lamu', 'Malindi', 'Kilifi', 'Kwale', 'Taita Taveta',
            'Machakos', 'Makueni', 'Kitui', 'Embu', 'Meru', 'Tharaka Nithi', 'Isiolo',
            'Marsabit', 'Samburu', 'Turkana', 'West Pokot', 'Baringo', 'Laikipia',
            'Nakuru', 'Narok', 'Kajiado', 'Kericho', 'Bomet', 'Kakamega', 'Vihiga',
            'Bungoma', 'Busia', 'Siaya', 'Kisumu', 'Homa Bay', 'Migori', 'Kisii',
            'Nyamira', 'Nyeri', 'Kirinyaga', 'Muranga', 'Kiambu', 'Nyandarua'
        ]
        
        for county in counties:
            if county.lower() in land_ref.lower():
                land_data['county'] = county
                break
        
        return land_data if any([land_data['lr_number'], land_data['plot_number'], 
                               land_data['certificate_number'], land_data['allotment_number']]) else land_data
