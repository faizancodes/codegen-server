from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl
from typing import List, Optional
import os
import re
import requests
import tempfile
import subprocess
from datetime import datetime
from codegen import Codebase
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = FastAPI(
    title="Dead Code Analyzer",
    description="API to analyze dead code in GitHub repositories using Codegen"
)

class RepoRequest(BaseModel):
    repo_url: HttpUrl

class PRResponse(BaseModel):
    pr_url: str
    branch_name: str
    removed_items: List[str]

class DeadCodeResult(BaseModel):
    file_path: str
    symbol_name: str
    symbol_type: str
    line_number: int

def get_symbol_line_number(symbol) -> int:
    """Helper function to safely get symbol line number."""
    try:
        # Get the source location from the source text
        source_lines = symbol.source.split('\n')
        return len(source_lines) if source_lines else 1
    except Exception:
        return 1

def parse_github_url(url: str) -> tuple:
    """Extract owner and repo from GitHub URL."""
    match = re.search(r"github\.com/([^/]+)/([^/]+)", str(url))
    if not match:
        raise HTTPException(status_code=400, detail="Invalid GitHub repository URL")
    
    return match.group(1), match.group(2)

@app.get("/")
async def root():
    return {"message": "Dead Code Analyzer API is running"}

@app.post("/analyze", response_model=List[DeadCodeResult])
async def analyze_dead_code(request: RepoRequest):
    try:
        # Extract owner/repo from GitHub URL
        match = re.search(r"github\.com/([^/]+/[^/]+)", str(request.repo_url))
        if not match:
            raise HTTPException(status_code=400, detail="Invalid GitHub repository URL")
        
        repo_path = match.group(1)
        
        # Initialize codebase from repo
        codebase = Codebase.from_repo(repo_path)
        
        dead_code = []
        
        # Analyze functions without usages
        for function in codebase.functions:
            if not function.usages:
                dead_code.append(
                    DeadCodeResult(
                        file_path=function.filepath,
                        symbol_name=function.name,
                        symbol_type="function",
                        line_number=get_symbol_line_number(function)
                    )
                )
        
        # Analyze classes without usages
        for class_ in codebase.classes:
            if not class_.usages:
                dead_code.append(
                    DeadCodeResult(
                        file_path=class_.filepath,
                        symbol_name=class_.name,
                        symbol_type="class",
                        line_number=get_symbol_line_number(class_)
                    )
                )
        
        return dead_code
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/create-pr", response_model=PRResponse)
async def create_pr_for_dead_code(request: RepoRequest):
    """
    Analyzes a repository for dead code, removes it, and creates a pull request with the changes.
    """
    # Get GitHub token from environment variable
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        raise HTTPException(status_code=500, detail="GITHUB_TOKEN environment variable is not set")
    
    try:
        # Extract owner and repo from GitHub URL
        owner, repo = parse_github_url(request.repo_url)
        repo_path = f"{owner}/{repo}"
        repo_url = f"https://github.com/{repo_path}.git"
        
        # Create a temporary directory to clone the repo
        with tempfile.TemporaryDirectory() as temp_dir:
            print(f"Created temporary directory: {temp_dir}")
            
            # Clone the repository
            clone_cmd = f"git clone https://x-access-token:{github_token}@github.com/{repo_path}.git {temp_dir}"
            subprocess.run(clone_cmd, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print(f"Cloned repository to {temp_dir}")
            
            # Initialize codebase from the cloned repo
            codebase = Codebase(temp_dir)
            
            # Find dead code
            dead_code_items = []
            removed_items = []
            
            # Find dead functions
            for function in codebase.functions:
                if not function.usages:
                    dead_code_items.append({
                        "symbol": function,
                        "type": "function"
                    })
            
            # Find dead classes
            for class_ in codebase.classes:
                if not class_.usages:
                    dead_code_items.append({
                        "symbol": class_,
                        "type": "class"
                    })
            
            if not dead_code_items:
                return PRResponse(
                    pr_url="",
                    branch_name="",
                    removed_items=[]
                )
            
            # Remove dead code using codegen
            for item in dead_code_items:
                symbol = item["symbol"]
                try:
                    # Remove the symbol from the codebase
                    symbol.remove()
                    removed_items.append(f"{item['type']} {symbol.name} in {symbol.filepath}")
                except Exception as e:
                    print(f"Error removing {item['type']} {symbol.name}: {str(e)}")
            
            # Commit changes to the codebase
            codebase.commit()
            
            # Create a new branch
            branch_name = f"dead-code-removal-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            subprocess.run(f"cd {temp_dir} && git checkout -b {branch_name}", 
                           shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print(f"Created new branch: {branch_name}")
            
            # Configure git
            subprocess.run(f"cd {temp_dir} && git config user.name 'Dead Code Analyzer'", 
                           shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            subprocess.run(f"cd {temp_dir} && git config user.email 'deadcode@example.com'", 
                           shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # Add and commit changes
            subprocess.run(f"cd {temp_dir} && git add .", 
                           shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            subprocess.run(f"cd {temp_dir} && git commit -m 'Remove dead code'", 
                           shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print("Committed changes")
            
            # Push the branch to GitHub
            push_cmd = f"cd {temp_dir} && git push -u https://x-access-token:{github_token}@github.com/{repo_path}.git {branch_name}"
            subprocess.run(push_cmd, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print(f"Pushed branch to GitHub: {branch_name}")
            
            # Create PR using GitHub API
            pr_url = create_github_pr(owner, repo, branch_name, removed_items, github_token)
            
            return PRResponse(
                pr_url=pr_url,
                branch_name=branch_name,
                removed_items=removed_items
            )
    
    except subprocess.CalledProcessError as e:
        error_message = f"Git error: {e.stderr.decode() if hasattr(e, 'stderr') else str(e)}"
        print(error_message)
        raise HTTPException(status_code=500, detail=error_message)
    except Exception as e:
        error_message = f"Error: {str(e)}"
        print(error_message)
        raise HTTPException(status_code=500, detail=error_message)

def create_github_pr(owner: str, repo: str, branch_name: str, removed_items: List[str], token: str) -> str:
    """
    Creates a GitHub pull request.
    """
    api_base = "https://api.github.com"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    try:
        # Get default branch
        repo_response = requests.get(f"{api_base}/repos/{owner}/{repo}", headers=headers)
        repo_response.raise_for_status()
        default_branch = repo_response.json()["default_branch"]
        
        # Create PR
        pr_body = "This PR removes dead code identified by the Dead Code Analyzer:\n\n"
        pr_body += "\n".join([f"- Removed {item}" for item in removed_items])
        
        pr_response = requests.post(
            f"{api_base}/repos/{owner}/{repo}/pulls",
            headers=headers,
            json={
                "title": "Remove Dead Code",
                "body": pr_body,
                "head": branch_name,
                "base": default_branch
            }
        )
        pr_response.raise_for_status()
        
        return pr_response.json()["html_url"]
    
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"GitHub API error: {str(e)}") 