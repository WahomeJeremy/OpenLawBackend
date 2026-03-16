import re
from django.core.management.base import BaseCommand
from django.db import transaction
from lands.models import Land


class Command(BaseCommand):
    help = 'Clean and normalize land data - extract LR/Block numbers and populate normalized fields'

    def handle(self, *args, **options):
        self.stdout.write('Starting land data cleaning process...')
        
        try:
            with transaction.atomic():
                lands = Land.objects.all()
                total_count = lands.count()
                processed = 0
                updated = 0
                
                for land in lands:
                    processed += 1
                    if self.process_land_record(land):
                        updated += 1
                    
                    if processed % 100 == 0:
                        self.stdout.write(f'Processed {processed}/{total_count} records...')
                
                self.stdout.write(
                    self.style.SUCCESS(f'Successfully processed {total_count} records, updated {updated} records')
                )
        
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error during data cleaning: {str(e)}')
            )

    def process_land_record(self, land):
        """Process a single land record and update normalized fields"""
        updated = False
        
        # Extract data from lr_number if it exists
        if land.lr_number:
            normalized_lr, title_system = self.extract_lr_info(land.lr_number)
            if normalized_lr != land.normalized_lr or title_system != land.title_system:
                land.normalized_lr = normalized_lr
                land.title_system = title_system
                updated = True
        else:
            # Try to extract from title_number if lr_number is empty
            if land.title_number:
                normalized_lr, title_system = self.extract_lr_from_case_title(land.title_number)
                if normalized_lr != land.normalized_lr or title_system != land.title_system:
                    land.normalized_lr = normalized_lr
                    land.title_system = title_system
                    updated = True
        
        if updated:
            land.save()
        
        return updated

    def extract_lr_info(self, text):
        """Extract normalized LR number and title system from text"""
        if not text:
            return None, None
        
        text = str(text).strip()
        
        # Check for BLOCK pattern first
        block_pattern = r'BLOCK\s*(\d+[/\-\w]*)'
        block_match = re.search(block_pattern, text, re.IGNORECASE)
        if block_match:
            block_number = block_match.group(1).strip()
            return block_number, 'BLOCK'
        
        # Check for LR pattern
        lr_pattern = r'LR\s*(NO\.?\s*)?(\d+[/\-\w]*)'
        lr_match = re.search(lr_pattern, text, re.IGNORECASE)
        if lr_match:
            lr_number = lr_match.group(2).strip()
            return lr_number, 'LR'
        
        # Check for standalone numbers that might be LR numbers
        # Look for patterns like "123/456" or "123-456"
        standalone_pattern = r'\b(\d+[/\-\w]{3,})\b'
        standalone_match = re.search(standalone_pattern, text)
        if standalone_match:
            number = standalone_match.group(1).strip()
            return number, 'LR'
        
        # Check for simple numeric patterns (at least 2 digits)
        simple_pattern = r'\b(\d{2,})\b'
        simple_match = re.search(simple_pattern, text)
        if simple_match:
            number = simple_match.group(1).strip()
            return number, 'LR'
        
        return None, None

    def extract_lr_from_case_title(self, case_title):
        """Extract LR numbers from case title when land_references is empty"""
        if not case_title:
            return None, None
        
        # Look for LR patterns in case title
        patterns = [
            r'LR\s*(NO\.?\s*)?(\d+[/\-\w]*)',
            r'L\.?\s*R\.?\s*(NO\.?\s*)?(\d+[/\-\w]*)',
            r'LAND\s+REFERENCE\s*(NO\.?\s*)?(\d+[/\-\w]*)',
            r'(\d{2,}[/\-\w]{2,})'  # Any number/letter combination like 123/456
        ]
        
        for pattern in patterns:
            match = re.search(pattern, case_title, re.IGNORECASE)
            if match:
                lr_number = match.groups()[-1].strip()  # Get the last group (the LR number)
                return lr_number, 'LR'
        
        return None, None
