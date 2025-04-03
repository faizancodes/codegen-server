from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from github import Github
import os
from dotenv import load_dotenv
from typing import List, Dict
import re
from pathlib import Path
import tempfile
import git
import ast
import logging

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="Dead Code Detector",
             description="API to analyze GitHub repositories for dead code")

# GitHub token from environment variables
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
if not GITHUB_TOKEN:
    raise ValueError("GitHub token not found in environment variables")

# Initialize GitHub client
github_client = Github(GITHUB_TOKEN)

# Pydantic models for request/response
class RepoRequest(BaseModel):
    repo_url: str

class DeadCodeResult(BaseModel):
    file_path: str
    unused_functions: List[str]
    unused_variables: List[str]

class AnalysisResponse(BaseModel):
    repository: str
    dead_code_findings: List[DeadCodeResult]

def clone_repository(repo_url: str) -> Path:
    """Clone a GitHub repository to a temporary directory."""
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir)
            git.Repo.clone_from(repo_url, repo_path)
            return repo_path
    except git.GitCommandError as e:
        logger.error(f"Failed to clone repository: {e}")
        raise HTTPException(status_code=400, detail="Failed to clone repository")

class FunctionVisitor(ast.NodeVisitor):
    """AST visitor to find unused functions and variables."""
    def __init__(self):
        self.defined_functions = set()
        self.called_functions = set()
        self.defined_variables = set()
        self.used_variables = set()
        
    def visit_FunctionDef(self, node):
        self.defined_functions.add(node.name)
        self.generic_visit(node)
        
    def visit_Call(self, node):
        if isinstance(node.func, ast.Name):
            self.called_functions.add(node.func.id)
        self.generic_visit(node)
        
    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Store):
            self.defined_variables.add(node.id)
        elif isinstance(node.ctx, ast.Load):
            self.used_variables.add(node.id)
            
def analyze_file(file_path: Path) -> DeadCodeResult:
    """Analyze a Python file for dead code."""
    try:
        with open(file_path, 'r') as f:
            tree = ast.parse(f.read())
            
        visitor = FunctionVisitor()
        visitor.visit(tree)
        
        unused_functions = visitor.defined_functions - visitor.called_functions
        unused_variables = visitor.defined_variables - visitor.used_variables
        
        # Filter out special cases
        unused_functions = {f for f in unused_functions 
                          if not any(special in str(file_path).lower() 
                                   for special in ['test', 'routes'])}
        
        return DeadCodeResult(
            file_path=str(file_path),
            unused_functions=list(unused_functions),
            unused_variables=list(unused_variables)
        )
    except Exception as e:
        logger.error(f"Error analyzing file {file_path}: {e}")
        return DeadCodeResult(
            file_path=str(file_path),
            unused_functions=[],
            unused_variables=[]
        )

def analyze_repository(repo_path: Path) -> List[DeadCodeResult]:
    """Analyze all Python files in a repository."""
    results = []
    for file_path in repo_path.rglob("*.py"):
        # Skip virtual environments and hidden directories
        if any(part.startswith('.') or part == 'venv' 
               for part in file_path.parts):
            continue
        result = analyze_file(file_path)
        if result.unused_functions or result.unused_variables:
            results.append(result)
    return results

@app.post("/analyze", response_model=AnalysisResponse)
async def analyze_repo(repo_request: RepoRequest):
    """Endpoint to analyze a GitHub repository for dead code."""
    try:
        # Extract repository information from URL
        repo_url = repo_request.repo_url
        if not repo_url.endswith('.git'):
            repo_url = f"{repo_url}.git"
            
        # Clone repository
        repo_path = clone_repository(repo_url)
        
        # Analyze repository
        findings = analyze_repository(repo_path)
        
        return AnalysisResponse(
            repository=repo_url,
            dead_code_findings=findings
        )
        
    except Exception as e:
        logger.error(f"Error analyzing repository: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error analyzing repository: {str(e)}"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
