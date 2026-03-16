import os
import django
import csv

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from lands.models import Land

# Clear existing data
Land.objects.all().delete()

# Import CSV data
csv_path = '/Users/mac/OpenLawBackend/Kenya_ELC_2019.csv'
with open(csv_path, 'r', encoding='utf-8-sig') as file:  # Use utf-8-sig to handle BOM
    reader = csv.DictReader(file)
    count = 0
    for row in reader:
        year_filed = None
        if row.get('year_filed') and row['year_filed'].isdigit():
            year_filed = int(row['year_filed'])
        
        Land.objects.create(
            title_number=row['case_title'][:300] if row['case_title'] else f'Case {count}',
            lr_number=row['land_references'][:255] if row['land_references'] else None,
            county=row['court_station'] or 'Unknown',
            judgment_type=row['judgment_type'] if row['judgment_type'] else None,
            plaintiff=row['plaintiff'][:255] if row['plaintiff'] else None,
            defendant=row['defendant'][:255] if row['defendant'] else None,
            court_station=row['court_station'] or 'Unknown',
            year_filed=year_filed
        )
        count += 1
        print(f'Imported {count}: {row["case_title"][:60]}...')

print(f'Total imported: {count}')
print(f'Database now has: {Land.objects.count()} records')
