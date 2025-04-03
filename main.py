from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl
from typing import List, Optional
from codegen import Codebase
import re

app = FastAPI(
    title="Dead Code Analyzer",
    description="API to analyze dead code in GitHub repositories using Codegen"
)

class RepoRequest(BaseModel):
    repo_url: HttpUrl

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