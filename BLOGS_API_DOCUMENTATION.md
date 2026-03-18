# 📚 Blogs API Documentation

## Overview
This document provides comprehensive API documentation for the Blogs application. The API follows RESTful conventions and supports full CRUD operations with advanced search capabilities.

**Base URLs:**
- **Local Development**: `http://127.0.0.1:8000/api/blogs/`
- **Production (Heroku)**: `https://openlaw-backend-d0f6778fbe50.herokuapp.com/api/blogs/`

---

## 🏗️ Data Models

### Category Model
```json
{
  "id": 1,
  "title": "Getting Started",
  "description": "The beginning of your legal journey - understanding the basics and preparing for what comes next",
  "tagline": "Every expert was once a beginner. Let us guide your first steps.",
  "order": 1,
  "is_active": true,
  "articles_count": 3
}
```

### Article Model
```json
{
  "id": 1,
  "category": 1,
  "category_title": "Getting Started",
  "title": "Understanding Legal Documents",
  "slug": "understanding-legal-documents",
  "content": "Legal documents can seem overwhelming at first, but they are essential for protecting your rights and interests...",
  "excerpt": "A beginner's guide to reading and understanding basic legal documents",
  "order": 1,
  "is_published": true,
  "created_at": "2026-03-18T08:30:00Z",
  "updated_at": "2026-03-18T08:30:00Z"
}
```

---

## 📖 Categories Endpoints

### 1. List All Categories
**GET** `/categories/`

**Description**: Retrieve all active categories representing user journey stages

**Response**:
```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "title": "Getting Started",
      "description": "The beginning of your legal journey...",
      "tagline": "Every expert was once a beginner...",
      "order": 1,
      "is_active": true,
      "articles_count": 3
    }
  ]
}
```

### 2. Get Category Details
**GET** `/categories/{id}/`

**Path Parameters**:
- `id` (integer): Category ID

**Response**:
```json
{
  "id": 1,
  "title": "Getting Started",
  "description": "The beginning of your legal journey...",
  "tagline": "Every expert was once a beginner...",
  "order": 1,
  "is_active": true,
  "articles_count": 3
}
```

### 3. Search Categories
**GET** `/categories/?search={query}`

**Query Parameters**:
- `search` (string, optional): Search term for title, description, and tagline

**Example**: `GET /categories/?search=legal`

### 4. Create Category
**POST** `/internal-dashboard/`

**Headers**:
```
Content-Type: application/json
```

**Request Body**:
```json
{
  "type": "category",
  "title": "Getting Started",
  "description": "The beginning of your legal journey - understanding the basics and preparing for what comes next",
  "tagline": "Every expert was once a beginner. Let us guide your first steps.",
  "order": 1,
  "is_active": true
}
```

**Required Fields**:
- `type`: Must be "category"
- `title` (string, max 255 chars)
- `description` (text)
- `tagline` (text)

**Optional Fields**:
- `order` (integer, default: 0)
- `is_active` (boolean, default: true)

**Response** (201 Created):
```json
{
  "id": 1,
  "title": "Getting Started",
  "description": "The beginning of your legal journey...",
  "tagline": "Every expert was once a beginner...",
  "order": 1,
  "is_active": true,
  "articles_count": 0
}
```

### 5. Update Category (Full)
**PUT** `/categories/{id}/edit/`

**Path Parameters**:
- `id` (integer): Category ID

**Request Body**: Same as create category (all fields required)

**Response**: Updated category object

### 6. Update Category (Partial)
**PATCH** `/categories/{id}/edit/`

**Path Parameters**:
- `id` (integer): Category ID

**Request Body**: Only fields to update
```json
{
  "title": "Updated Category Title"
}
```

**Response**: Updated category object

### 7. Delete Category
**DELETE** `/categories/{id}/edit/`

**Path Parameters**:
- `id` (integer): Category ID

**Response**: 204 No Content

---

## 📄 Articles Endpoints

### 1. List All Articles
**GET** `/articles/`

**Query Parameters**:
- `search` (string, optional): Search term for title, content, excerpt, category title
- `category` (integer, optional): Filter by category ID

**Example**: `GET /articles/?search=legal&category=1`

**Response**:
```json
{
  "count": 5,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "category": 1,
      "category_title": "Getting Started",
      "title": "Understanding Legal Documents",
      "slug": "understanding-legal-documents",
      "content": "Legal documents can seem overwhelming...",
      "excerpt": "A beginner's guide to reading legal documents",
      "order": 1,
      "is_published": true,
      "created_at": "2026-03-18T08:30:00Z",
      "updated_at": "2026-03-18T08:30:00Z"
    }
  ]
}
```

### 2. Get Article Details
**GET** `/articles/{slug}/`

**Path Parameters**:
- `slug` (string): Article slug

**Response**:
```json
{
  "id": 1,
  "category": {
    "id": 1,
    "title": "Getting Started",
    "description": "The beginning of your legal journey...",
    "tagline": "Every expert was once a beginner...",
    "order": 1,
    "is_active": true,
    "articles_count": 3
  },
  "title": "Understanding Legal Documents",
  "slug": "understanding-legal-documents",
  "content": "Legal documents can seem overwhelming at first...",
  "excerpt": "A beginner's guide to reading legal documents",
  "created_at": "2026-03-18T08:30:00Z",
  "updated_at": "2026-03-18T08:30:00Z"
}
```

### 3. Get Article by Category
**GET** `/categories/{category_id}/articles/{slug}/`

**Path Parameters**:
- `category_id` (integer): Category ID
- `slug` (string): Article slug

**Response**: Same as article details

### 4. Search Articles
**GET** `/articles/?search={query}`

**Query Parameters**:
- `search` (string): Search term for title, content, excerpt, category title
- `category` (integer): Filter by category ID

**Example**: `GET /articles/?search=documents`

### 5. Create Article
**POST** `/internal-dashboard/`

**Headers**:
```
Content-Type: application/json
```

**Request Body**:
```json
{
  "type": "article",
  "category": 1,
  "title": "Understanding Legal Documents",
  "slug": "understanding-legal-documents",
  "content": "Legal documents can seem overwhelming at first, but they are essential for protecting your rights and interests. This guide will help you understand the basics of legal documentation, from simple agreements to complex contracts. We'll cover common terminology, formatting conventions, and red flags to watch for when reviewing documents.",
  "excerpt": "A beginner's guide to reading and understanding basic legal documents",
  "order": 1,
  "is_published": true
}
```

**Required Fields**:
- `type`: Must be "article"
- `category` (integer): Existing category ID
- `title` (string, max 255 chars)
- `slug` (string): URL-friendly version of title (must be unique)
- `content` (text): Article content

**Optional Fields**:
- `excerpt` (string, max 500 chars): Brief summary
- `order` (integer, default: 0): Display order within category
- `is_published` (boolean, default: true): Publication status

**Response** (201 Created):
```json
{
  "id": 1,
  "category": 1,
  "category_title": "Getting Started",
  "title": "Understanding Legal Documents",
  "slug": "understanding-legal-documents",
  "content": "Legal documents can seem overwhelming...",
  "excerpt": "A beginner's guide to reading legal documents",
  "order": 1,
  "is_published": true,
  "created_at": "2026-03-18T08:30:00Z",
  "updated_at": "2026-03-18T08:30:00Z"
}
```

### 6. Update Article (Full)
**PUT** `/articles/{id}/edit/`

**Path Parameters**:
- `id` (integer): Article ID

**Request Body**: Same as create article (all fields required)

**Response**: Updated article object

### 7. Update Article (Partial)
**PATCH** `/articles/{id}/edit/`

**Path Parameters**:
- `id` (integer): Article ID

**Request Body**: Only fields to update
```json
{
  "title": "Updated Article Title",
  "content": "Updated article content..."
}
```

**Response**: Updated article object

### 8. Delete Article
**DELETE** `/articles/{id}/edit/`

**Path Parameters**:
- `id` (integer): Article ID

**Response**: 204 No Content

---

## 🔍 Advanced Search Endpoint

### Search Articles and Categories
**GET** `/search/`

**Query Parameters**:
- `search` (string, optional): Search term for title, content, excerpt, and all category fields
- `category` (integer, optional): Filter by category ID
- `order_by` (string, optional): Sort results
  - `category__order` (default): Sort by category order, then article order
  - `order`: Sort by article order
  - `title`: Sort by title alphabetically
  - `created_at`: Sort by creation date (oldest first)
  - `-created_at`: Sort by creation date (newest first)

**Examples**:
```
GET /search/?search=legal
GET /search/?search=beginner&category=1
GET /search/?order_by=title
GET /search/?search=document&order_by=-created_at
```

**Response**:
```json
{
  "count": 3,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "category": 1,
      "category_title": "Getting Started",
      "title": "Understanding Legal Documents",
      "slug": "understanding-legal-documents",
      "content": "Legal documents can seem overwhelming...",
      "excerpt": "A beginner's guide to reading legal documents",
      "order": 1,
      "is_published": true,
      "created_at": "2026-03-18T08:30:00Z",
      "updated_at": "2026-03-18T08:30:00Z"
    }
  ],
  "search_params": {
    "search": "legal",
    "category": "",
    "order_by": "category__order"
  }
}
```

---

## 🛠️ Internal Dashboard Endpoint

### Manage Content
**GET** `/internal-dashboard/`
**POST** `/internal-dashboard/`
**PUT** `/internal-dashboard/{id}/`
**DELETE** `/internal-dashboard/{id}/`

**Description**: Internal endpoint for content management (supports both categories and articles)

**GET Response**:
```json
{
  "categories": [...],
  "articles": [...]
}
```

**POST Request**: Same as individual create endpoints but includes `type` field

---

## 📋 Endpoint Summary

| Method | Endpoint | Purpose | Auth Required |
|--------|----------|---------|---------------|
| GET | `/categories/` | List all categories | No |
| GET | `/categories/{id}/` | Get category details | No |
| GET | `/categories/?search=` | Search categories | No |
| POST | `/internal-dashboard/` | Create category | Yes |
| PUT | `/categories/{id}/edit/` | Update category | Yes |
| PATCH | `/categories/{id}/edit/` | Partial update category | Yes |
| DELETE | `/categories/{id}/edit/` | Delete category | Yes |
| GET | `/articles/` | List all articles | No |
| GET | `/articles/{slug}/` | Get article details | No |
| GET | `/articles/?search=` | Search articles | No |
| POST | `/internal-dashboard/` | Create article | Yes |
| PUT | `/articles/{id}/edit/` | Update article | Yes |
| PATCH | `/articles/{id}/edit/` | Partial update article | Yes |
| DELETE | `/articles/{id}/edit/` | Delete article | Yes |
| GET | `/search/` | Advanced search | No |
| GET | `/internal-dashboard/` | Dashboard data | Yes |

---

## 🌐 Environment Configuration

### Local Development
```bash
# Base URL
http://127.0.0.1:8000/api/blogs/

# Example calls
curl -X GET http://127.0.0.1:8000/api/blogs/categories/
curl -X POST http://127.0.0.1:8000/api/blogs/internal-dashboard/ \
  -H "Content-Type: application/json" \
  -d '{"type": "category", "title": "Test", "description": "Test desc", "tagline": "Test tagline"}'
```

### Production (Heroku)
```bash
# Base URL
https://openlaw-backend-d0f6778fbe50.herokuapp.com/api/blogs/

# Example calls
curl -X GET https://openlaw-backend-d0f6778fbe50.herokuapp.com/api/blogs/categories/
curl -X POST https://openlaw-backend-d0f6778fbe50.herokuapp.com/api/blogs/internal-dashboard/ \
  -H "Content-Type: application/json" \
  -d '{"type": "category", "title": "Test", "description": "Test desc", "tagline": "Test tagline"}'
```

---

## 🚨 Error Responses

### Validation Errors (400)
```json
{
  "title": ["This field is required."],
  "category": ["Invalid category ID."]
}
```

### Not Found (404)
```json
{
  "detail": "Not found."
}
```

### Method Not Allowed (405)
```json
{
  "detail": "Method \"POST\" not allowed."
}
```

### Server Error (500)
```json
{
  "detail": "Internal server error."
}
```

---

## 📝 Notes for Frontend Developers

1. **Search is case-insensitive** and uses partial matching
2. **Category order** determines the user journey flow
3. **Article order** determines display within each category
4. **Slugs must be unique** across all articles
5. **Published articles only** appear in public endpoints
6. **Internal dashboard** requires authentication for write operations
7. **Pagination** is enabled for list endpoints
8. **CORS** is configured for cross-origin requests

---

## 🔄 Common Workflows

### Typical User Journey Flow
1. `GET /categories/` - Show all journey stages
2. `GET /categories/{id}/` - Show stage details
3. `GET /articles/?category={id}` - Show articles in that stage
4. `GET /articles/{slug}/` - Read specific article

### Content Management Flow
1. `POST /internal-dashboard/` - Create category
2. `POST /internal-dashboard/` - Create articles in category
3. `PUT/PATCH /categories/{id}/edit/` - Update category
4. `PUT/PATCH /articles/{id}/edit/` - Update articles
5. `DELETE /articles/{id}/edit/` - Remove articles if needed

### Search and Discovery
1. `GET /search/?search=keyword` - Global search
2. `GET /categories/?search=keyword` - Category-specific search
3. `GET /articles/?search=keyword&category={id}` - Filtered search

---

*Last Updated: March 18, 2026*
