# OpenLaw Backend API Documentation
## Statement of Work (SOW) - Frontend Integration

### Table of Contents
1. [Authentication & Setup](#authentication--setup)
2. [Core Endpoints](#core-endpoints)
3. [Land Management](#land-management)
4. [Case Management](#case-management)
5. [Certificate Management](#certificate-management)
6. [Blog Management](#blog-management)
7. [Legal Email Applications](#legal-email-applications)
8. [Error Handling](#error-handling)
9. [Data Models](#data-models)

---

## Authentication & Setup

### Base URL
```
Development: http://localhost:8000/api/
Production: https://your-domain.com/api/
```

### Headers
```json
{
  "Content-Type": "application/json",
  "Accept": "application/json"
}
```

### CORS Configuration
The backend is configured to accept requests from:
- `http://localhost:3000`
- `http://127.0.0.1:3000`

---

## Core Endpoints

### Legal Email Application System

#### 1. Submit Legal Email Application
**Endpoint:** `POST /api/core/legal-email-applications/`

**Description:** Submit a new @legal.ke email application

**Request Body:**
```json
{
  "full_name": "Jane Mary Doe",
  "phone_number": "+254 700 000 000",
  "account_type": "personal",
  "occupation": "lawyer",
  "lsk_admission_no": "P.105/12345/24",
  "current_email": "yourname@example.com",
  "desired_email": "firstname.lastname"
}
```

**Field Validation:**
- `full_name`: Required, max 200 characters
- `phone_number`: Required, max 20 characters
- `account_type`: Required, options: `["personal", "business"]`
- `occupation`: Required, options: `["lawyer", "judge", "legal_assistant", "law_student", "other"]`
- `lsk_admission_no`: Optional, max 50 characters
- `current_email`: Required, valid email format
- `desired_email`: Required, max 100 characters (username part only)

**Success Response (201 Created):**
```json
{
  "id": 1,
  "full_name": "Jane Mary Doe",
  "phone_number": "+254 700 000 000",
  "account_type": "personal",
  "occupation": "lawyer",
  "lsk_admission_no": "P.105/12345/24",
  "current_email": "yourname@example.com",
  "desired_email": "firstname.lastname",
  "status": "pending",
  "created_at": "2026-02-27T17:23:29.135560+03:00",
  "updated_at": "2026-02-27T17:23:29.135560+03:00"
}
```

**Error Response (400 Bad Request):**
```json
{
  "full_name": ["This field is required."],
  "current_email": ["Enter a valid email address."]
}
```



## Land Management

### 1. Single Land Search
**Endpoint:** `GET /api/lands/search/`

**Description:** Search for a single land parcel by various identifiers

**Query Parameters:**
- `q` (required): Search query (title number, LR number, plot number, etc.)

**Example Request:**
```
GET /api/lands/search/?q=10821/53
```

**Success Response (200 OK):**
```json
{
  "query": "10821/53",
  "results": [
    {
      "id": "332",
      "cases_count": 1,
      "title_number": "10821/53",
      "lr_number": "10821/53",
      "plot_number": "10821/53",
      "certificate_number": null,
      "allotment_number": null,
      "county": null,
      "created_at": "2026-02-25T14:38:21.447538+03:00"
    },
    {
      "id": "333",
      "cases_count": 1,
      "title_number": "No.10821/53",
      "lr_number": null,
      "plot_number": "No.10821/53",
      "certificate_number": null,
      "allotment_number": null,
      "county": null,
      "created_at": "2026-02-25T14:38:21.449092+03:00"
    }
  ],
  "count": 2
}
```

**Error Response (400 Bad Request):**
```json
{
  "error": "Search query is required"
}
```

### 2. Bulk Land Search
**Endpoint:** `POST /api/lands/bulk-search/`

**Description:** Search for multiple land parcels in a single request

**Request Body:**
```json
{
  "queries": ["10821/53", "12345", "LR 209/123", "Plot 789"]
}
```

**Validation:**
- `queries`: Required, array of strings
- Minimum: 1 query
- Maximum: 50 queries
- Each query: max 255 characters

**Success Response (200 OK):**
```json
{
  "results": [
    {
      "query": "10821/53",
      "results": [
        {
          "id": "332",
          "cases_count": 1,
          "title_number": "10821/53",
          "lr_number": "10821/53",
          "plot_number": "10821/53",
          "certificate_number": null,
          "allotment_number": null,
          "county": null,
          "created_at": "2026-02-25T14:38:21.447538+03:00"
        },
        {
          "id": "333",
          "cases_count": 1,
          "title_number": "No.10821/53",
          "lr_number": null,
          "plot_number": "No.10821/53",
          "certificate_number": null,
          "allotment_number": null,
          "county": null,
          "created_at": "2026-02-25T14:38:21.449092+03:00"
        }
      ],
      "count": 2
    },
    {
      "query": "12345",
      "results": [],
      "count": 0
    },
    {
      "query": "LR 209/123",
      "results": [],
      "count": 0
    },
    {
      "query": "Plot 789",
      "results": [],
      "count": 0
    }
  ]
}
```

**Error Response (400 Bad Request):**
```json
{
  "queries": {
    "0": ["This field may not be blank."]
  }
}
```

### 3. Get Land Details
**Endpoint:** `GET /api/lands/{land_id}/`

**Description:** Get detailed information about a specific land parcel

**URL Parameters:**
- `land_id`: UUID of the land parcel

**Success Response (200 OK):**
```json
{
  "id": "332",
  "cases_count": 1,
  "title_number": "10821/53",
  "lr_number": "10821/53",
  "plot_number": "10821/53",
  "certificate_number": null,
  "allotment_number": null,
  "county": null,
  "created_at": "2026-02-25T14:38:21.447538+03:00"
}
```

**Error Response (404 Not Found):**
```json
{
  "detail": "Not found."
}
```

---

## Case Management

### 1. List Cases
**Endpoint:** `GET /api/cases/`

**Description:** Retrieve all court cases with pagination

**Query Parameters:**
- `page`: Page number (default: 1)
- `page_size`: Items per page (default: 20)

**Success Response (200 OK):**
```json
{
  "count": 1500,
  "next": "http://localhost:8000/api/cases/?page=2",
  "previous": null,
  "results": [
    {
      "id": 1,
      "case_number": "KEELC/2019/950",
      "case_name": "Rashid Kogi Muturi v Screen Check Limited",
      "year": 2019,
      "status": "Ruling",
      "court": "Thika",
      "summary": "Case summary text...",
      "plaintiff": "Rashid Kogi Muturi",
      "defendant": "Screen Check Limited",
      "land": "332"
    }
  ]
}
```

### 2. Get Case Details
**Endpoint:** `GET /api/cases/{case_id}/`

**Description:** Get detailed information about a specific case

**Success Response (200 OK):**
```json
{
  "id": 1,
  "case_number": "KEELC/2019/950",
  "case_name": "Rashid Kogi Muturi v Screen Check Limited",
  "year": 2019,
  "status": "Ruling",
  "court": "Thika",
  "summary": "Full case summary text...",
  "plaintiff": "Rashid Kogi Muturi",
  "defendant": "Screen Check Limited",
  "land": "332",
  "created_at": "2026-02-25T14:38:21.447538+03:00",
  "updated_at": "2026-02-25T14:38:21.447538+03:00"
}
```

---

## Certificate Management

### 1. Generate Certificate
**Endpoint:** `POST /api/certificates/generate/{land_id}/`

**Description:** Generate a land due diligence certificate

**URL Parameters:**
- `land_id`: Integer ID of the land parcel

**Success Response (201 Created):**
```json
{
  "id": "d3bbaf35-d7d7-4554-8ed4-72d053516f67",
  "land_title": "10821/53",
  "ongoing_cases_count": 1,
  "resolved_cases_count": 0,
  "unknown_status_cases_count": 0,
  "total_cases_count": 1,
  "has_ongoing_litigation": true,
  "ongoing_cases": [
    {
      "id": 949,
      "case_number": "KEELC/2019/950",
      "case_name": "Rashid Kogi Muturi v Screen Check Limited",
      "year": 2019,
      "status": "Ruling",
      "plaintiff": "Rashid Kogi Muturi",
      "defendant": "Screen Check Limited",
      "outcome": "",
      "court_station": "Thika"
    }
  ],
  "resolved_cases": [],
  "unknown_status_cases": [],
  "certificate_type": "CASE_LINKED",
  "generated_at": "2026-02-27T17:23:29.135560+03:00",
  "pdf_file": "/media/certificates/certificate_d3bbaf35-d7d7-4554-8ed4-72d053516f67.pdf",
  "land": 332
}
```

**Error Response (404 Not Found):**
```json
{
  "error": "Land not found"
}
```

### 2. Download Certificate
**Endpoint:** `GET /api/certificates/download/{certificate_id}/`

**Description:** Download certificate PDF file

**URL Parameters:**
- `certificate_id`: UUID of the certificate

**Success Response (200 OK):**
- Returns PDF file as download
- Content-Type: `application/pdf`
- Content-Disposition: `attachment; filename="certificate_{uuid}.pdf"`

**Error Response (404 Not Found):**
```json
{
  "error": "PDF file not found"
}
```

---

## Blog Management

### 1. List Blog Posts
**Endpoint:** `GET /api/blogs/`

**Description:** Retrieve all blog posts with pagination

**Success Response (200 OK):**
```json
{
  "count": 25,
  "next": "http://localhost:8000/api/blogs/?page=2",
  "previous": null,
  "results": [
    {
      "id": 1,
      "title": "Understanding Land Due Diligence in Kenya",
      "content": "Blog content...",
      "author": "Legal Team",
      "published_date": "2026-02-27T10:00:00Z",
      "created_at": "2026-02-27T09:00:00Z",
      "updated_at": "2026-02-27T09:00:00Z"
    }
  ]
}
```

### 2. Get Blog Post Details
**Endpoint:** `GET /api/blogs/{blog_id}/`

**Description:** Get detailed information about a specific blog post

**Success Response (200 OK):**
```json
{
  "id": 1,
  "title": "Understanding Land Due Diligence in Kenya",
  "content": "Full blog content with detailed explanation...",
  "author": "Legal Team",
  "published_date": "2026-02-27T10:00:00Z",
  "created_at": "2026-02-27T09:00:00Z",
  "updated_at": "2026-02-27T09:00:00Z"
}
```

---

## Error Handling

### Standard Error Response Format
```json
{
  "error": "Error description",
  "details": {
    "field_name": ["Validation error message"]
  }
}
```

### Common HTTP Status Codes
- `200 OK`: Request successful
- `201 Created`: Resource created successfully
- `400 Bad Request`: Invalid request data
- `401 Unauthorized`: Authentication required
- `403 Forbidden`: Permission denied
- `404 Not Found`: Resource not found
- `500 Internal Server Error`: Server error

### Validation Error Examples
```json
{
  "full_name": ["This field is required."],
  "current_email": ["Enter a valid email address."],
  "queries": {
    "0": ["This field may not be blank."]
  }
}
```

---

## Data Models

### Legal Email Application Model
```json
{
  "id": "integer",
  "full_name": "string (max 200)",
  "phone_number": "string (max 20)",
  "account_type": "string (personal|business)",
  "occupation": "string (lawyer|judge|legal_assistant|law_student|other)",
  "lsk_admission_no": "string (max 50, optional)",
  "current_email": "email",
  "desired_email": "string (max 100)",
  "status": "string (pending|approved|rejected)",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

### Land Model
```json
{
  "id": "uuid",
  "title_number": "string (max 255)",
  "lr_number": "string (max 255, optional)",
  "plot_number": "string (max 255, optional)",
  "certificate_number": "string (max 255, optional)",
  "allotment_number": "string (max 255, optional)",
  "county": "string (max 100, optional)",
  "cases_count": "integer (calculated)",
  "created_at": "datetime"
}
```

### Case Model
```json
{
  "id": "integer",
  "case_number": "string",
  "case_name": "string",
  "year": "integer",
  "status": "string (Ruling|Judgment|null)",
  "court": "string",
  "summary": "text",
  "plaintiff": "string",
  "defendant": "string",
  "land": "uuid (foreign key)",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

### Certificate Model
```json
{
  "id": "uuid",
  "land": "uuid (foreign key)",
  "certificate_type": "string (CASE_LINKED|CLEARANCE)",
  "pdf_file": "file path",
  "generated_at": "datetime",
  "land_title": "string (calculated)",
  "ongoing_cases_count": "integer (calculated)",
  "resolved_cases_count": "integer (calculated)",
  "unknown_status_cases_count": "integer (calculated)",
  "total_cases_count": "integer (calculated)",
  "has_ongoing_litigation": "boolean (calculated)"
}
```

---

## Integration Guidelines

### 1. Rate Limiting
- No explicit rate limiting implemented
- Recommended: Implement client-side throttling for bulk operations

### 2. File Uploads
- Certificate PDFs are stored in `/media/certificates/`
- Maximum file size: 10MB per certificate
- Supported formats: PDF only

### 3. Search Optimization
- Use specific search terms for better results
- Bulk search supports up to 50 queries per request
- Search is case-insensitive

### 4. Email Notifications
- Legal email applications automatically send notifications to `support@legal.ke`
- Email configuration requires proper SMTP settings in `.env`

### 5. Certificate Generation
- Certificates are generated in HTML format (temporarily)
- PDF conversion will be implemented with WeasyPrint
- Each certificate includes factual land and case information only

---

## Testing Examples

### Test Legal Email Application
```bash
curl -X POST http://localhost:8000/api/core/legal-email-applications/ \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "John Doe",
    "phone_number": "+254 712 345 678",
    "account_type": "personal",
    "occupation": "lawyer",
    "lsk_admission_no": "P.105/12345/24",
    "current_email": "john.doe@example.com",
    "desired_email": "john.doe"
  }'
```

### Test Bulk Land Search
```bash
curl -X POST http://localhost:8000/api/lands/bulk-search/ \
  -H "Content-Type: application/json" \
  -d '{"queries": ["10821/53", "12345", "LR 209/123"]}'
```

### Test Certificate Generation
```bash
curl -X POST http://localhost:8000/api/certificates/generate/332/ \
  -H "Content-Type: application/json"
```

---

## Deployment Considerations

### Environment Variables
```bash
# Database Configuration
DB_NAME=openlawdb
DB_USER=openlawuser
DB_PASSWORD="openlaw44@#99yhtb"
DB_HOST=localhost
DB_PORT=5432

# Email Configuration
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=your-email@gmail.com
SUPPORT_EMAIL=support@legal.ke

# Django Settings
SECRET_KEY=your-secret-key
DEBUG=False
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
```

### Production Checklist
- [ ] Set DEBUG=False
- [ ] Configure proper ALLOWED_HOSTS
- [ ] Set up production database
- [ ] Configure email settings
- [ ] Set up static files serving
- [ ] Configure SSL certificates
- [ ] Set up monitoring and logging

---

## Support & Maintenance

### API Versioning
- Current version: v1
- Version included in URL: `/api/v1/` (future implementation)
- Backward compatibility maintained for minor updates

### Monitoring
- Monitor certificate generation success rates
- Track email notification delivery
- Monitor search performance metrics
- Log all application submissions

### Backup Strategy
- Database backups daily
- Certificate PDF backups weekly
- Media file backups monthly

---

*This documentation covers all current API endpoints and is intended for frontend development teams integrating with the OpenLaw Backend system.*
