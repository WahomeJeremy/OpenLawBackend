from django.core.management.base import BaseCommand
from cases.models import Case
from lands.models import Land

class Command(BaseCommand):
    help = 'Clear all case and land data'

    def handle(self, *args, **options):
        # Clear all cases first (this will also clear many-to-many relationships)
        case_count = Case.objects.count()
        Case.objects.all().delete()
        
        # Clear all lands
        land_count = Land.objects.count()
        Land.objects.all().delete()
        
        self.stdout.write(self.style.SUCCESS(f'Deleted {case_count} cases and {land_count} land records'))
