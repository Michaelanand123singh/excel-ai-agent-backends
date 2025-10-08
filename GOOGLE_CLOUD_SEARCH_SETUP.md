# Google Cloud Search Setup Guide

This guide will help you set up Google Cloud Search as the primary search engine for the Excel AI Agent system.

## Prerequisites

1. **Google Cloud Project**: You need an active Google Cloud Project
2. **Billing Enabled**: Google Cloud Search requires billing to be enabled
3. **Required APIs**: Cloud Search API must be enabled

## Step 1: Enable Google Cloud Search API

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Select your project
3. Navigate to **APIs & Services** → **Library**
4. Search for "Cloud Search API"
5. Click **Enable**

## Step 2: Create Service Account

1. Navigate to **IAM & Admin** → **Service Accounts**
2. Click **Create Service Account**
3. Fill in the details:
   - **Name**: `search-service-account`
   - **Description**: `Service account for Excel AI Agent search functionality`
4. Click **Create and Continue**
5. Grant the following roles:
   - **Cloud Search Admin**
   - **Cloud Search Indexer**
6. Click **Done**

## Step 3: Create and Download Service Account Key

1. Find your service account in the list
2. Click on the service account name
3. Go to **Keys** tab
4. Click **Add Key** → **Create new key**
5. Select **JSON** format
6. Click **Create**
7. Download the JSON file and store it securely

## Step 4: Set Environment Variables

Add the following environment variables to your deployment:

```bash
# Google Cloud Search Configuration
GOOGLE_CLOUD_PROJECT_ID=your-project-id
GOOGLE_CLOUD_SEARCH_INDEX_ID=parts-search-index
GOOGLE_APPLICATION_CREDENTIALS=/path/to/your/service-account-key.json
```

### For Cloud Run Deployment:

1. Go to **Cloud Run** → **Your Service** → **Edit & Deploy New Revision**
2. Go to **Variables & Secrets** tab
3. Add the environment variables:
   - `GOOGLE_CLOUD_PROJECT_ID`: Your project ID
   - `GOOGLE_CLOUD_SEARCH_INDEX_ID`: `parts-search-index` (or your preferred name)
   - `GOOGLE_APPLICATION_CREDENTIALS`: Upload the JSON key file or use Secret Manager

### For Local Development:

Create a `.env` file in your backend directory:

```env
GOOGLE_CLOUD_PROJECT_ID=your-project-id
GOOGLE_CLOUD_SEARCH_INDEX_ID=parts-search-index
GOOGLE_APPLICATION_CREDENTIALS=/path/to/your/service-account-key.json
```

## Step 5: Install Dependencies

The required dependencies are already added to `requirements.txt`:

```bash
pip install google-cloud-search==0.1.0
pip install google-auth==2.23.4
```

## Step 6: Deploy and Test

1. Deploy your application with the new environment variables
2. Upload a test Excel file
3. Check the logs to see if Google Cloud Search indexing is successful
4. Test search functionality

## How It Works

### Search Priority Order:
1. **Google Cloud Search** (Primary) - Ultra-fast, sub-second results
2. **Elasticsearch** (Fallback) - Fast, good for large datasets
3. **PostgreSQL** (Final Fallback) - Reliable, comprehensive search

### Data Flow:
1. **Upload**: Excel file → Database + Google Cloud Search indexing
2. **Search**: Query → Google Cloud Search → Elasticsearch → PostgreSQL
3. **Results**: Same format as before, with confidence scores and match types

### Benefits:
- **Ultra-fast search**: Sub-second response times even with 1 crore records
- **Scalable**: Handles massive datasets efficiently
- **Reliable**: Multiple fallback layers ensure search always works
- **Compatible**: Same API and response format as existing system

## Monitoring and Troubleshooting

### Check Google Cloud Search Status:
```python
from app.services.search_engine.google_cloud_search_client import GoogleCloudSearchClient

gcs_client = GoogleCloudSearchClient()
print(f"Google Cloud Search available: {gcs_client.is_available()}")
```

### Common Issues:

1. **Authentication Error**: Check `GOOGLE_APPLICATION_CREDENTIALS` path
2. **Permission Denied**: Ensure service account has proper roles
3. **API Not Enabled**: Verify Cloud Search API is enabled
4. **Billing**: Ensure billing is enabled for your project

### Logs to Monitor:
- `✅ Google Cloud Search is available`
- `✅ Google Cloud Search indexing completed`
- `🔍 Using Google Cloud Search for single/bulk search`

## Performance Expectations

- **Single Search**: < 100ms
- **Bulk Search (1,000 parts)**: < 2 seconds
- **Bulk Search (10,000 parts)**: < 10 seconds
- **Bulk Search (100,000 parts)**: < 60 seconds

## Cost Considerations

Google Cloud Search pricing is based on:
- **Index Size**: Number of documents indexed
- **Search Queries**: Number of search requests
- **Storage**: Data stored in the index

For 1 crore records, expect approximately:
- **Indexing**: One-time cost for initial indexing
- **Search**: Pay-per-query model
- **Storage**: Based on data size

## Security Best Practices

1. **Service Account**: Use least privilege principle
2. **Key Management**: Store keys in Secret Manager for production
3. **Access Control**: Limit who can access the search index
4. **Audit Logging**: Enable Cloud Audit Logs for monitoring

## Support

If you encounter issues:
1. Check the application logs
2. Verify environment variables
3. Test with a small dataset first
4. Check Google Cloud Console for API errors
