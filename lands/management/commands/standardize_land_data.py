import re
import unicodedata
from django.core.management.base import BaseCommand
from django.db import transaction
from lands.models import Land, SearchableReference


class Command(BaseCommand):
    help = 'Standardize land data and create searchable reference index'

    def handle(self, *args, **options):
        self.stdout.write('Starting land data standardization process...')
        
        try:
            with transaction.atomic():
                # Clear existing searchable references
                SearchableReference.objects.all().delete()
                
                lands = Land.objects.all()
                total_count = lands.count()
                processed = 0
                
                for land in lands:
                    processed += 1
                    try:
                        self.process_land_record(land)
                    except Exception as e:
                        self.stdout.write(f'Error processing land {land.id}: {str(e)}')
                        
                    if processed % 100 == 0:
                        self.stdout.write(f'Processed {processed}/{total_count} records...')
                
                self.stdout.write(
                    self.style.SUCCESS(f'Successfully processed {total_count} records')
                )
                self.stdout.write(f'Created {SearchableReference.objects.count()} searchable references')
        
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error during data standardization: {str(e)}')
            )

    def process_land_record(self, land):
        """Process a single land record and create searchable references"""
        
        # Process land_references field
        if land.lr_number and land.lr_number.strip():
            self.extract_and_create_references(land, land.lr_number, from_land_references=True)
        
        # Process other fields
        if land.plot_number and land.plot_number.strip():
            self.extract_and_create_references(land, land.plot_number, reference_type='PLOT')
        
        if land.certificate_number and land.certificate_number.strip():
            self.extract_and_create_references(land, land.certificate_number, reference_type='CERTIFICATE')
        
        if land.allotment_number and land.allotment_number.strip():
            self.extract_and_create_references(land, land.allotment_number, reference_type='ALLOTMENT')
        
        # Secondary title scan if land_references is empty
        if not land.lr_number or not land.lr_number.strip():
            self.scan_title_for_references(land)

    def extract_and_create_references(self, land, text, reference_type='LR', from_land_references=False):
        """Extract and create searchable references from text"""
        if not text:
            return
        
        # Ensure text is string
        text = str(text)
        
        # Clean invisible characters and extra whitespace
        cleaned_text = self.clean_text(text)
        
        # Split multi-entries by semicolon or 'and'
        entries = self.split_multi_entries(cleaned_text)
        
        for i, entry in enumerate(entries):
            # Extract core identifier using regex
            core_identifier = self.extract_core_identifier(entry)
            
            if core_identifier:
                # Normalize the identifier
                normalized = self.normalize_identifier(core_identifier)
                
                # Determine reference type
                if reference_type == 'LR':
                    ref_type = self.determine_reference_type(entry)
                else:
                    ref_type = reference_type
                
                # Create searchable reference
                SearchableReference.objects.create(
                    land=land,
                    reference_text=normalized,
                    reference_type=ref_type,
                    is_primary=(from_land_references and i == 0)  # First entry from land_references is primary
                )

    def clean_text(self, text):
        """Clean invisible characters and extra whitespace"""
        if not text:
            return ""
        
        # Remove invisible characters like \xa0
        text = unicodedata.normalize('NFKD', text)
        text = ''.join(char for char in text if not unicodedata.combining(char))
        
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text.strip())
        
        return text

    def split_multi_entries(self, text):
        """Split text by semicolon or 'and'"""
        if not text:
            return []
        
        # Split by semicolon first
        entries = [entry.strip() for entry in text.split(';')]
        
        # Further split entries that contain 'and'
        final_entries = []
        for entry in entries:
            and_splits = re.split(r'\s+and\s+', entry, flags=re.IGNORECASE)
            final_entries.extend([split.strip() for split in and_splits if split.strip()])
        
        return [entry for entry in final_entries if entry]

    def extract_core_identifier(self, text):
        """Extract only the core identifier using regex"""
        if not text:
            return ""
        
        # Look for specific patterns first - most specific to least specific
        patterns = [
            # LR patterns
            r'LR\s*(?:NO\.?\s*)?([A-Za-z0-9\s\/\-\.\(\)]+)',
            r'L\.?\s*R\.?\s*(?:NO\.?\s*)?([A-Za-z0-9\s\/\-\.\(\)]+)',
            r'LAND\s+REFERENCE\s*(?:NO\.?\s*)?([A-Za-z0-9\s\/\-\.\(\)]+)',
            
            # Block patterns  
            r'BLOCK\s*(\d+[/\-\w]*)',
            r'MUNICIPALITY\s*BLOCK\s*(\d+[/\-\w]*)',
            
            # Plot patterns
            r'PLOT\s*(NO\.?\s*)?([A-Za-z0-9\s\/\-\.\(\)]+)',
            r'PARCEL\s*(NO\.?\s*)?([A-Za-z0-9\s\/\-\.\(\)]+)',
            
            # Simple number patterns like "123/456"
            r'\b(\d{2,}[/\-][A-Za-z0-9]{2,})\b',
            r'\b(\d{3,})\b',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                identifier = match.group(1).strip()
                # Clean up the identifier
                identifier = re.sub(r'\s+', ' ', identifier)  # Multiple spaces to single
                identifier = re.sub(r'[.,]', '', identifier)  # Remove dots and commas
                return identifier
        
        return ""

    def normalize_identifier(self, identifier):
        """Normalize the identifier by removing prefixes and standardizing format"""
        if not identifier:
            return ""
        
        # Only remove standalone prefixes, not when they're part of the identifier
        identifier = re.sub(r'^(LR|L\.?R\.?|LAND\s+REFERENCE|PLOT|PARCEL|BLOCK|MUNICIPALITY\s*BLOCK)(?=\s|$)', '', identifier, flags=re.IGNORECASE)
        
        # Remove dots and commas, but keep slashes and dashes
        identifier = re.sub(r'[.,]', '', identifier)
        
        # Convert to uppercase and strip
        identifier = identifier.upper().strip()
        
        # Replace multiple spaces with single space
        identifier = re.sub(r'\s+', ' ', identifier)
        
        return identifier

    def determine_reference_type(self, text):
        """Determine reference type from text"""
        text_upper = text.upper()
        
        if 'BLOCK' in text_upper or 'MUNICIPALITY' in text_upper:
            return 'BLOCK'
        elif 'PLOT' in text_upper or 'PARCEL' in text_upper:
            return 'PLOT'
        elif 'CERTIFICATE' in text_upper:
            return 'CERTIFICATE'
        elif 'ALLOTMENT' in text_upper:
            return 'ALLOTMENT'
        else:
            return 'LR'

    def scan_title_for_references(self, land):
        """Scan case title for LR patterns if land_references is empty"""
        if not land.title_number:
            return
        
        # Look for LR patterns in case title
        patterns = [
            r'LR\s*(?:NO\.?\s*)?([A-Za-z0-9\s\/\-\.\(\)]+)',
            r'L\.?\s*R\.?\s*(?:NO\.?\s*)?([A-Za-z0-9\s\/\-\.\(\)]+)',
            r'LAND\s+REFERENCE\s*(?:NO\.?\s*)?([A-Za-z0-9\s\/\-\.\(\)]+)',
            r'BLOCK\s*(\d+[/\-\w]*)',
            r'(\d{2,}[/\-\w]{2,})',  # Any number/letter combination like 123/456
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, land.title_number, re.IGNORECASE)
            for match in matches:
                normalized = self.normalize_identifier(match)
                if normalized:
                    ref_type = self.determine_reference_type(match)
                    SearchableReference.objects.create(
                        land=land,
                        reference_text=normalized,
                        reference_type=ref_type,
                        is_primary=False  # From title scan, not primary
                    )
