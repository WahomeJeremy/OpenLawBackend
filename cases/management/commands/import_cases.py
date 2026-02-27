import csv
import re
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db import models
from lands.models import Land
from cases.models import Case


class Command(BaseCommand):
    help = 'Import cases from CSV file'

    def add_arguments(self, parser):
        parser.add_argument('--file', type=str, required=True, help='Path to CSV file')

    def handle(self, *args, **options):
        file_path = options['file']
        
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                
                with transaction.atomic():
                    for row_num, row in enumerate(reader, 1):
                        try:
                            self.process_row(row, row_num)
                        except Exception as e:
                            self.stdout.write(
                                self.style.ERROR(f'Error processing row {row_num}: {str(e)}')
                            )
                            continue
                
                self.stdout.write(
                    self.style.SUCCESS('Successfully imported cases from CSV')
                )
        
        except FileNotFoundError:
            self.stdout.write(
                self.style.ERROR(f'File not found: {file_path}')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error reading file: {str(e)}')
            )

    def process_row(self, row, row_num):
        """Process a single CSV row"""
        # Handle both 2013 and 2019 CSV formats
        if 'case_id' in row:
            # 2013 CSV format
            case_id = row.get('case_id', '').strip()
            plaintiff = row.get('plaintiff', '').strip()
            defendant = row.get('defendant', '').strip()
            court = row.get('court', '').strip()
            year_filed = self.parse_int(row.get('year_filed', 0))
            land_references = row.get('land_references', '').strip()
            case_title = row.get('case_title', '').strip()
            url = row.get('url', '').strip()
            
            # Extract case number from case_title for 2013 format
            case_number = self.extract_case_number(case_title)
            case_name = case_title
            court_station = court
            judgment_type = "Judgment"  # Default for 2013
            parties = f'Plaintiff: {plaintiff}\nDefendant: {defendant}'
            
        else:
            # 2019 CSV format (existing logic)
            year_filed = self.parse_int(row.get('year_filed', 0))
            court_station = row.get('court_station', '').strip()
            plaintiff = row.get('plaintiff', '').strip()
            defendant = row.get('defendant', '').strip()
            case_title = row.get('case_title', '').strip()
            judgment_type = row.get('judgment_type', '').strip()
            land_references = row.get('land_references', '').strip()
            url = row.get('url', '').strip()

            # Extract case number from case_title (format: [2019] KEELC 1 (KLR))
            case_number = self.extract_case_number(case_title)
            case_name = case_title
            court = court_station
            parties = f'Plaintiff: {plaintiff}\nDefendant: {defendant}'

        if not case_title:
            raise ValueError('Case title is required')
        
        # Create or get case
        case, created = Case.objects.get_or_create(
            case_number=case_number,
            defaults={
                'case_name': case_name,
                'year': year_filed,
                'court': court_station if 'case_id' in row else court,
                'status': judgment_type,
                'summary': parties,
                'parties': parties,
                'plaintiff': plaintiff,
                'defendant': defendant,
            }
        )

        if created:
            self.stdout.write(f'Created case: {case_number}')
        else:
            self.stdout.write(f'Case already exists: {case_number}')

        # Process land references if they exist
        if land_references:
            land_refs = self.extract_land_references_from_text(land_references)
            
            for ref in land_refs:
                land = self.get_or_create_land(ref)
                case.lands.add(land)
                self.stdout.write(f'Linked case {case_number} to land {ref}')

    def extract_case_number(self, case_title):
        """Extract case number from case title"""
        # Look for pattern like [2019] KEELC 1 (KLR)
        import re
        pattern = r'\[(\d{4})\]\s+KEELC\s+(\d+)\s+\(KLR\)'
        match = re.search(pattern, case_title)
        if match:
            year, number = match.groups()
            return f"KEELC/{year}/{number}"
        
        # Fallback: use first part of case title
        return case_title.split(' v ')[0][:100]

    def extract_land_references_from_text(self, text):
        """Extract land references from land_references column"""
        if not text:
            return []
        
        refs = []
        # Split by semicolon or comma
        parts = re.split(r'[;,]', text)
        
        for part in parts:
            part = part.strip()
            if part:
                # Look for LR patterns
                lr_patterns = [
                    r'L\.R\.\s*NO\.?\s*([A-Z0-9/\-\.]+)',
                    r'LR\s*NO\.?\s*([A-Z0-9/\-\.]+)',
                    r'L\.R\.\s*([A-Z0-9/\-\.]+)',
                    r'LR\s*([A-Z0-9/\-\.]+)',
                    r'([A-Z0-9/\-]+\s*(?:BLOCK|Block|MUNICIPALITY|Municipality)\s*[0-9/\-]+)',
                ]
                
                for pattern in lr_patterns:
                    matches = re.findall(pattern, part, re.IGNORECASE)
                    refs.extend(matches)
        
        # Clean and deduplicate
        cleaned_refs = []
        for ref in refs:
            cleaned = ref.strip().strip('.;')
            if cleaned and len(cleaned) > 3:  # Minimum length for meaningful reference
                cleaned_refs.append(cleaned)
        
        return list(set(cleaned_refs))  # Remove duplicates

    def get_or_create_land(self, reference):
        """Get or create land record from reference"""
        if not reference or len(reference.strip()) < 3:
            return None
            
        normalized_ref = Land.normalize_lr(reference)
        
        # Try to find existing land by various fields
        land = Land.objects.filter(
            models.Q(title_number__icontains=reference) |
            models.Q(lr_number__icontains=reference) |
            models.Q(plot_number__icontains=reference) |
            models.Q(certificate_number__icontains=reference) |
            models.Q(allotment_number__icontains=reference)
        ).first()

        if land:
            return land

        # Create new land record with proper field assignment
        land_data = self.detect_land_fields(reference)
        land = Land.objects.create(**land_data)
        self.stdout.write(f'Created land: {reference} -> {land_data}')
        return land

    def detect_land_fields(self, reference):
        """Detect the appropriate field for the land reference and return dict"""
        ref_upper = reference.upper().strip()
        
        # LR Number patterns - more comprehensive
        lr_patterns = [
            'L.R.', 'LR ', ' LR', 'L.R NO', 'LR NO', 'LR NO.', 'L.R.NO'
        ]
        if any(pattern in ref_upper for pattern in lr_patterns):
            # Extract the actual number after LR
            import re
            lr_match = re.search(r'(?:L\.R\.?|LR)\s*NO\.?\s*([A-Z0-9/\-\.]+)', ref_upper)
            if lr_match:
                lr_number = lr_match.group(1)
                return {
                    'lr_number': lr_number,
                    'title_number': lr_number  # Also set as title for search
                }
        
        # Check if this looks like an LR number (format from case context)
        # Numbers that were mentioned as L.R. in cases but extracted without prefix
        if self.is_likely_lr_number(reference):
            return {
                'lr_number': reference,
                'title_number': reference
            }
        
        # Block patterns (Municipality Block, etc.)
        elif any(pattern in ref_upper for pattern in ['BLOCK', 'MUNICIPALITY', 'MUNICPALITY']):
            return {
                'plot_number': reference,
                'title_number': reference
            }
        
        # Certificate patterns
        elif any(pattern in ref_upper for pattern in ['CERTIFICATE', 'CERT', 'TITLE']):
            return {
                'certificate_number': reference,
                'title_number': reference
            }
        
        # Allotment patterns
        elif any(pattern in ref_upper for pattern in ['ALLOTMENT', 'ALLOT']):
            return {
                'allotment_number': reference,
                'title_number': reference
            }
        
        # Plot patterns (contains numbers and slashes, typical plot format)
        elif any(char.isdigit() for char in reference) and '/' in reference:
            return {
                'plot_number': reference,
                'title_number': reference
            }
        
        # Default to title_number
        else:
            return {
                'title_number': reference
            }

    def is_likely_lr_number(self, reference):
        """Check if a reference is likely an LR number based on format patterns"""
        # Common LR number patterns from Kenyan land system
        ref_upper = reference.upper().strip()
        
        # Pattern 1: 5-6 digits followed by / and more digits (e.g., 10821/531)
        if re.match(r'^\d{4,6}/\d+', ref_upper):
            return True
            
        # Pattern 2: Contains specific area codes known to be LR numbers
        lr_area_codes = ['MN', 'III', 'IV', 'KIIRUA', 'KAMAGAMBO', 'KABONDO', 'NGINDA']
        if any(code in ref_upper for code in lr_area_codes) and '/' in ref_upper:
            return True
            
        return False

    def parse_int(self, value):
        """Parse integer value safely"""
        try:
            return int(value) if value else None
        except (ValueError, TypeError):
            return None
