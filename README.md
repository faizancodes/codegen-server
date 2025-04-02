# Dead Code Analyzer API

A FastAPI server that analyzes GitHub repositories for dead code using the Codegen SDK.

## Requirements

- Python 3.12 or higher
- pip or uv package manager
- GitHub Personal Access Token with repo scope

## Installation

1. Clone this repository:
```bash
git clone <your-repo-url>
cd <repo-directory>
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
# Copy the example environment file
cp .env.example .env

# Edit .env with your GitHub credentials
# Required variables:
# - GITHUB_TOKEN: Your GitHub Personal Access Token
# - GITHUB_USERNAME: Your GitHub username
# - GITHUB_EMAIL: Your GitHub email
```

## Running the Server

Start the server using uvicorn:

```bash
uvicorn main:app --reload
```

The server will start at `http://localhost:8000`

## API Endpoints

### 1. GET /
Root endpoint returning API information.

### 2. POST /analyze-dead-code
Analyzes a GitHub repository for dead code and optionally creates a pull request to remove it.

Request body:
```json
{
    "repo_url": "https://github.com/owner/repo",
    "create_pr": true  // Optional, defaults to false
}
```

Response:
```json
{
    "repository": "owner/repo",
    "analysis": {
        "unused_functions": [
            {
                "name": "function_name",
                "filepath": "path/to/file",
                "source": "function function_name() { ... }"
            }
        ],
        "unused_classes": [
            {
                "name": "class_name",
                "filepath": "path/to/file",
                "source": "class class_name { ... }"
            }
        ],
        "total_unused_items": 2
    },
    "pull_request": {  // Only included if create_pr is true
        "url": "https://github.com/owner/repo/pull/123",
        "number": 123
    }
}
```

When `create_pr` is set to `true`, the API will:
1. Create a new branch named `chore/remove-dead-code`
2. Remove all detected dead code
3. Create a pull request with detailed information about removed code
4. Return the PR URL and number in the response

## API Documentation

Once the server is running, you can access:
- Interactive API documentation at: `http://localhost:8000/docs`
- Alternative API documentation at: `http://localhost:8000/redoc`

## GitHub Authentication

The API requires GitHub credentials to create pull requests. These should be set in your `.env` file:

1. Create a GitHub Personal Access Token:
   - Go to GitHub Settings > Developer Settings > Personal Access Tokens
   - Generate a new token with 'repo' scope
   - Copy the token

2. Set up your .env file:
   ```env
   GITHUB_TOKEN=your_github_personal_access_token
   GITHUB_USERNAME=your_github_username
   GITHUB_EMAIL=your_github_email
   ```

3. The API will automatically use these credentials when creating pull requests 