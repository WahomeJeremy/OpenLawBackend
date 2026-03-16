# OpenLaw Backend API

Land Due Diligence Platform (Kenya) - Backend API System

## Overview

OpenLaw is a comprehensive land due diligence platform for Kenya that enables users to:
- Verify Kenyan land (via Title/Plot/Certificate/Allotment/LR Number)
- View related court cases and case details
- See number of disputes associated with land parcels
- Generate legal certificates (Case-Linked or Clearance)
- Access land-related blog posts

## Technology Stack

- **Backend**: Django 5 + Django REST Framework
- **Database**: PostgreSQL (with PostGIS support for Phase 2)
- **Certificate Generation**: WeasyPrint
- **CSV Ingestion**: Django Management Commands
- **API Documentation**: Django REST Framework

## Project Structure

```
openlaw_backend/
├── config/                 # Django project configuration
├── core/                   # Core utilities and base classes
├── lands/                  # Land records management
├── cases/                  # Court case records
├── certificates/           # Certificate generation system
├── blogs/                  # Blog management system
├── scripts/                # Utility scripts and management tools
│   ├── import_data.py      # Data import utilities
│   └── test_email.py       # Email configuration testing
├── docs/                   # Documentation
│   └── API_DOCUMENTATION.md # Complete API reference
├── data/                   # Data files
│   ├── Kenya_ELC_2013_clean.csv
│   └── Kenya_ELC_2019.csv
├── templates/              # HTML templates for certificates
│   └── certificate_test.html
├── media/                  # Uploaded files (certificates)
├── staticfiles/            # Static files
├── manage.py
├── requirements.txt
├── .env                    # Environment variables (gitignored)
└── README.md
```

## Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd openlaw_backend
   ```

2. **Create and activate virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   Create a `.env` file in the project root:
   ```env
   DB_NAME=openlawdb
   DB_USER=openlawuser
   DB_PASSWORD=your_password
   DB_HOST=localhost
   DB_PORT=5432
   SECRET_KEY=your_secret_key
   DEBUG=True
   ALLOWED_HOSTS=localhost,127.0.0.1
   ```

5. **Set up PostgreSQL database**
   ```sql
   CREATE DATABASE openlawdb;
   CREATE USER openlawuser WITH PASSWORD 'your_password';
   GRANT ALL PRIVILEGES ON DATABASE openlawdb TO openlawuser;
   ```

6. **Run migrations**
   ```bash
   python manage.py makemigrations
   python manage.py migrate
   ```

7. **Create superuser (optional)**
   ```bash
   python manage.py createsuperuser
   ```

8. **Run the development server**
   ```bash
   python manage.py runserver
   ```

## API Endpoints

### Land Search
- `GET /api/lands/search/?q=<query>` - Search land by title/LR/plot/certificate/allotment number
- `GET /api/lands/<uuid:pk>/` - Get detailed land information

### Cases
- `GET /api/cases/` - List all cases
- `GET /api/cases/<uuid:pk>/` - Get detailed case information

### Certificates
- `POST /api/certificates/generate/<uuid:land_id>/` - Generate certificate for land
- `GET /api/certificates/<uuid:pk>/download/` - Download certificate PDF

### Blogs
- `GET /api/blogs/` - List published blog posts
- `GET /api/blogs/<slug:slug>/` - Get blog post details
- `GET/POST/PUT/DELETE /api/blogs/internal-dashboard/` - Internal blog management (hidden URL)

## Data Import

### Import Cases from CSV
Use the management command to import case data:

```bash
python manage.py import_cases --file data/Kenya_ELC_2019.csv
```

### Test Email Configuration
Test the email setup before using the contact forms:

```bash
python scripts/test_email.py
```

#### Expected CSV Format
The CSV should contain the following columns (case-insensitive):
- `case_number` (required)
- `case_name`
- `year`
- `court`
- `status`
- `summary`
- `parties`
- `land_reference` or `lr_number` or `title_number` (optional)

#### Data Normalization
The system automatically normalizes land references:
- "LR No. 12345/67" → "12345/67"
- "L.R. 12345/67" → "12345/67"
- "LR 12345/67" → "12345/67"

## Certificate Generation

The system automatically determines certificate type:
- **Case-Linked Certificate**: Generated when land has associated court cases
- **Clearance Certificate**: Generated when land has no cases

Certificates include:
- Land details (title, LR, plot, certificate, allotment numbers)
- Case information (if applicable)
- Unique certificate ID
- Official OpenLaw stamp
- Generation timestamp

## Features

### Search System
Full-text search across all land identifiers:
- Title Number
- LR Number
- Plot Number
- Certificate Number
- Allotment Number

### Certificate System
- Automatic certificate type detection
- PDF generation with WeasyPrint
- Professional certificate templates
- Download functionality

### Blog System
- Public blog posts for land-related content
- Hidden admin dashboard for content management
- Published/draft status control

## Development

### Running Tests
```bash
python manage.py test
```

### Database Migrations
```bash
python manage.py makemigrations
python manage.py migrate
```

### Collect Static Files
```bash
python manage.py collectstatic
```

## Phase 2 Features (Future)

- PostGIS integration for geospatial data
- Google Maps API integration
- Live map view with parcel boundaries
- Geolocation overlay
- Directions functionality

## Security Considerations

- Hidden blog management URL
- Rate limiting recommended for search endpoints
- HTTPS only in production
- SQL injection prevention via Django ORM

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is proprietary to OpenLaw Kenya.

## Support

For technical support, please contact the development team.
