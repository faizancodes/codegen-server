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

### 2. POST /analyze
Analyzes a GitHub repository for dead code.

Request body:
```json
{
    "repo_url": "https://github.com/owner/repo"
}
```

Response:
```json
[
    {
        "file_path": "path/to/file.js",
        "symbol_name": "unusedFunction",
        "symbol_type": "function",
        "line_number": 42
    },
    {
        "file_path": "path/to/file.js",
        "symbol_name": "UnusedClass",
        "symbol_type": "class",
        "line_number": 100
    }
]
```

### 3. POST /create-pr
Analyzes a GitHub repository for dead code, removes it, and creates a pull request with the changes.

Request body:
```json
{
    "repo_url": "https://github.com/owner/repo"
}
```

Response:
```json
{
    "pr_url": "https://github.com/owner/repo/pull/123",
    "branch_name": "dead-code-removal-20230615123456",
    "removed_items": [
        "function unusedFunction in path/to/file.js",
        "class UnusedClass in path/to/file.js"
    ]
}
```

## API Documentation

Once the server is running, you can access:
- Interactive API documentation at: `http://localhost:8000/docs`
- Alternative API documentation at: `http://localhost:8000/redoc`

## GitHub Authentication

The API requires a GitHub Personal Access Token to create pull requests. This should be set in your `.env` file:

1. Create a GitHub Personal Access Token:
   - Go to GitHub Settings > Developer Settings > Personal Access Tokens
   - Generate a new token with 'repo' scope
   - Copy the token

2. Set up your .env file:
   ```env
   GITHUB_TOKEN=your_github_personal_access_token
   ```

3. The API will automatically use this token when creating pull requests 