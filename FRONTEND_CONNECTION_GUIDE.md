# Frontend Connection Guide

## Backend API Connection

Your Django backend is deployed and ready for frontend integration.

### API Base URL
```
https://openlaw-backend-d0f6778fbe50.herokuapp.com
```

### Available Endpoints

#### Cases API
```
GET  /api/cases/           - List all cases (paginated)
GET  /api/cases/{id}/      - Get specific case
POST /api/cases/           - Create new case
PUT  /api/cases/{id}/      - Update case
DELETE /api/cases/{id}/    - Delete case
```

#### Lands API
```
GET  /api/lands/           - List all lands
GET  /api/lands/{id}/      - Get specific land
POST /api/lands/           - Create new land
PUT  /api/lands/{id}/      - Update land
DELETE /api/lands/{id}/    - Delete land
```

#### Certificates API
```
GET  /api/certificates/    - List all certificates
GET  /api/certificates/{id}/ - Get specific certificate
POST /api/certificates/   - Create new certificate
PUT  /api/certificates/{id}/ - Update certificate
DELETE /api/certificates/{id}/ - Delete certificate
```

#### Blogs API
```
GET  /api/blogs/           - List all blogs
GET  /api/blogs/{id}/      - Get specific blog
POST /api/blogs/           - Create new blog
PUT  /api/blogs/{id}/      - Update blog
DELETE /api/blogs/{id}/    - Delete blog
```

### CORS Configuration
The backend is configured to allow requests from:
- `http://localhost:3000`
- `http://127.0.0.1:3000`

For production, you'll need to add your frontend domain to the CORS allowed origins.

### API Response Format

#### Success Response (200 OK)
```json
{
    "count": 2725,
    "next": "https://openlaw-backend-d0f6778fbe50.herokuapp.com/api/cases/?page=2",
    "previous": null,
    "results": [
        {
            "id": 1,
            "case_number": "KEELC 1",
            "case_name": "Vitalis Okoth Ngesa & 2 others v Kenya Builders and Concrete Limited & another [2019] KEELC 1 (KLR)",
            "year": 2019,
            "court": "NAIROBI",
            "status": "Judgment",
            "summary": "",
            "parties": "Vitalis Okoth Ngesa & 2 others vs Kenya Builders and Concrete Limited & another",
            "plaintiff": "Vitalis Okoth Ngesa & 2 others",
            "defendant": "Kenya Builders and Concrete Limited & another",
            "created_at": "2024-02-28T00:00:00Z"
        }
    ]
}
```

#### Error Response (400/404/500)
```json
{
    "error": "Error message",
    "status_code": 400
}
```

### Frontend Implementation Examples

#### React/Fetch Example
```javascript
const API_BASE_URL = 'https://openlaw-backend-d0f6778fbe50.herokuapp.com';

// Fetch all cases with pagination
const fetchCases = async (page = 1) => {
    try {
        const response = await fetch(`${API_BASE_URL}/api/cases/?page=${page}`);
        const data = await response.json();
        return data;
    } catch (error) {
        console.error('Error fetching cases:', error);
        throw error;
    }
};

// Create new case
const createCase = async (caseData) => {
    try {
        const response = await fetch(`${API_BASE_URL}/api/cases/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(caseData),
        });
        const data = await response.json();
        return data;
    } catch (error) {
        console.error('Error creating case:', error);
        throw error;
    }
};
```

#### Axios Example
```javascript
import axios from 'axios';

const API_BASE_URL = 'https://openlaw-backend-d0f6778fbe50.herokuapp.com';

const api = axios.create({
    baseURL: API_BASE_URL,
    headers: {
        'Content-Type': 'application/json',
    },
});

// Get all cases
export const getCases = (page = 1) => {
    return api.get(`/api/cases/?page=${page}`);
};

// Get single case
export const getCase = (id) => {
    return api.get(`/api/cases/${id}/`);
};

// Create case
export const createCase = (caseData) => {
    return api.post('/api/cases/', caseData);
};

// Update case
export const updateCase = (id, caseData) => {
    return api.put(`/api/cases/${id}/`, caseData);
};

// Delete case
export const deleteCase = (id) => {
    return api.delete(`/api/cases/${id}/`);
};
```

### Environment Configuration

#### React (.env)
```env
REACT_APP_API_BASE_URL=https://openlaw-backend-d0f6778fbe50.herokuapp.com
```

#### Vue (.env)
```env
VUE_APP_API_BASE_URL=https://openlaw-backend-d0f6778fbe50.herokuapp.com
```

### Authentication (Future Enhancement)
Currently, the API doesn't require authentication. If you need to add authentication:

1. Django REST Framework JWT tokens
2. Session-based authentication
3. Token-based authentication

### Pagination
All list endpoints support pagination:
- `?page=2` - Go to page 2
- `?page_size=50` - Show 50 items per page

### Search and Filtering
You can add search parameters to endpoints:
```
/api/cases/?search=land
/api/cases/?court=NAIROBI
/api/cases/?year=2019
```

### Error Handling
Always handle HTTP status codes:
- `200` - Success
- `201` - Created
- `400` - Bad Request
- `401` - Unauthorized
- `404` - Not Found
- `500` - Server Error

### Testing the Connection
```javascript
// Test connection
fetch('https://openlaw-backend-d0f6778fbe50.herokuapp.com/api/cases/')
    .then(response => response.json())
    .then(data => console.log('Connected successfully!', data))
    .catch(error => console.error('Connection failed:', error));
```

### Production Considerations
1. Update CORS settings to include your production frontend domain
2. Implement authentication for sensitive operations
3. Add rate limiting to prevent abuse
4. Set up monitoring and logging
5. Consider API versioning for future updates
