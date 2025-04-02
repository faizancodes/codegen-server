from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl
from codegen import Codebase
from codegen.configs.models.codebase import CodebaseConfig
from codegen.configs.models.secrets import SecretsConfig
from codegen.shared.enums.programming_language import ProgrammingLanguage
import tempfile
import os
import shutil
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get GitHub credentials from environment
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GITHUB_USERNAME = os.getenv('GITHUB_USERNAME')
GITHUB_EMAIL = os.getenv('GITHUB_EMAIL')

# Validate required environment variables
if not all([GITHUB_TOKEN, GITHUB_USERNAME, GITHUB_EMAIL]):
    raise ValueError(
        "Missing required environment variables. Please ensure GITHUB_TOKEN, "
        "GITHUB_USERNAME, and GITHUB_EMAIL are set in your .env file"
    )

app = FastAPI(
    title="Dead Code Analyzer",
    description="API to analyze GitHub repositories for dead code",
    version="1.0.0"
)

class RepoRequest(BaseModel):
    repo_url: HttpUrl
    create_pr: Optional[bool] = False
    language: Optional[ProgrammingLanguage] = None

def get_symbol_location(symbol):
    """Helper function to safely get symbol location information."""
    try:
        # Get the source location information
        source = symbol.source
        filepath = symbol.filepath
        
        # For safety, ensure we have the required information
        if not all([source, filepath]):
            return None
            
        return {
            'name': symbol.name,
            'filepath': filepath,
            'source': source
        }
    except Exception:
        return None

def create_pr_description(unused_items):
    """Create a detailed PR description for dead code removal."""
    description = "## Dead Code Removal\n\n"
    description += "This PR removes unused code identified by the Dead Code Analyzer.\n\n"
    
    if unused_items['unused_functions']:
        description += "\n### Removed Functions\n"
        for func in unused_items['unused_functions']:
            description += f"\n- `{func['name']}` from `{func['filepath']}`\n"
            description += "```typescript\n"
            description += func['source']
            description += "\n```\n"
    
    if unused_items['unused_classes']:
        description += "\n### Removed Classes\n"
        for class_ in unused_items['unused_classes']:
            description += f"\n- `{class_['name']}` from `{class_['filepath']}`\n"
            description += "```typescript\n"
            description += class_['source']
            description += "\n```\n"
    
    return description

def detect_language(filepath: str) -> ProgrammingLanguage:
    """Detect the programming language based on file extensions."""
    if any(filepath.endswith(ext) for ext in ['.ts', '.tsx', '.js', '.jsx']):
        return ProgrammingLanguage.TYPESCRIPT
    elif any(filepath.endswith(ext) for ext in ['.py']):
        return ProgrammingLanguage.PYTHON
    return ProgrammingLanguage.TYPESCRIPT  # Default to typescript for modern web projects

def is_test_file(filepath: str) -> bool:
    """Check if a file is a test file."""
    test_patterns = [
        '.test.', '.spec.', '__tests__',
        'test/', 'tests/', 'spec/', 'e2e/'
    ]
    return any(pattern in filepath for pattern in test_patterns)

def should_analyze_file(filepath: str) -> bool:
    """Determine if a file should be analyzed for dead code."""
    # Skip test files
    if is_test_file(filepath):
        return False
        
    # Skip certain directories and file types
    skip_patterns = [
        'node_modules/', '.next/', '.git/',
        'dist/', 'build/', 'coverage/',
        '.d.ts', '.min.js', '.bundle.js',
        # Skip specific problematic files/patterns
        'hero-workflow.tsx', 
        '(landing)/components/'  # Skip the landing components directory causing issues
    ]
    return not any(pattern in filepath for pattern in skip_patterns)

@app.post("/analyze-dead-code")
async def analyze_dead_code(request: RepoRequest):
    """
    Analyze a GitHub repository for dead code and optionally create a PR to remove it.
    """
    try:
        # Extract repo owner and name from URL
        parts = str(request.repo_url).rstrip('/').split('/')
        if len(parts) < 5 or 'github.com' not in parts:
            raise HTTPException(status_code=400, detail="Invalid GitHub repository URL")
        
        owner_repo = f"{parts[-2]}/{parts[-1]}"
        
        # Create a temporary directory for the analysis
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                # Setup configurations
                secrets_config = SecretsConfig(
                    github_token=GITHUB_TOKEN
                )
                
                # Create a more robust codebase config
                codebase_config = CodebaseConfig(
                    debug=True,  # Enable debug mode for better error messages
                    skip_node_modules=True,
                    skip_build=True,
                    skip_tests=True,
                    max_file_size=1000000,
                    ignore_patterns=[
                        "**/node_modules/**",
                        "**/.next/**",
                        "**/dist/**",
                        "**/build/**",
                        "**/*.d.ts"
                    ]
                )

                # Determine language - now returns ProgrammingLanguage enum
                detected_language = request.language or detect_language(owner_repo)
                
                try:
                    codebase = Codebase.from_repo(
                        owner_repo,
                        tmp_dir=temp_dir,
                        config=codebase_config,
                        secrets=secrets_config,
                        language=detected_language
                    )
                except AssertionError as e:
                    error_msg = str(e)
                    print(f"Warning: Encountered an assertion error during codebase initialization: {error_msg}")
                    
                    if "has_edge" in error_msg or "Edge" in error_msg:
                        print("Retrying with more restrictive settings...")
                        
                        restricted_config = CodebaseConfig(
                            debug=True,
                            skip_node_modules=True,
                            skip_build=True,
                            skip_tests=True,
                            max_file_size=500000,
                            ignore_patterns=[
                                "**/node_modules/**",
                                "**/.next/**",
                                "**/dist/**",
                                "**/build/**",
                                "**/*.d.ts",
                                "**/*.test.*",
                                "**/*.spec.*",
                                "**/tests/**",
                                "**/e2e/**"
                            ],
                            parse_comments=False,
                            resolve_types=False
                        )
                        
                        codebase = Codebase.from_repo(
                            owner_repo,
                            tmp_dir=temp_dir,
                            config=restricted_config,
                            secrets=secrets_config,
                            language=detected_language
                        )
                except Exception as e:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to initialize codebase: {str(e)}"
                    )
                
                # Find unused functions and classes
                unused_functions = []
                unused_classes = []
                
                # Track items to be removed
                items_to_remove = []
                
                # Process each file
                for file in codebase.files:
                    if not should_analyze_file(file.filepath):
                        continue
                        
                    # Process functions in the file
                    for function in file.functions:
                        try:
                            if not function.usages and not function.is_exported:
                                location = get_symbol_location(function)
                                if location:
                                    unused_functions.append(location)
                                    items_to_remove.append(function)
                        except Exception as e:
                            print(f"Warning: Error processing function {function.name} in {file.filepath}: {str(e)}")
                            continue
                    
                    # Process classes in the file
                    for class_ in file.classes:
                        try:
                            if not class_.usages and not class_.is_exported:
                                location = get_symbol_location(class_)
                                if location:
                                    unused_classes.append(location)
                                    items_to_remove.append(class_)
                        except Exception as e:
                            print(f"Warning: Error processing class {class_.name} in {file.filepath}: {str(e)}")
                            continue
                
                analysis_result = {
                    'repository': owner_repo,
                    'analysis': {
                        'unused_functions': unused_functions,
                        'unused_classes': unused_classes,
                        'total_unused_items': len(unused_functions) + len(unused_classes)
                    }
                }
                
                # If create_pr is True and there are items to remove, create a PR
                if request.create_pr and items_to_remove:
                    try:
                        # Create a new branch for the changes
                        branch_name = "chore/remove-dead-code"
                        codebase.checkout(branch=branch_name, create_if_missing=True)
                        
                        # Configure git user
                        os.system(f'git config --global user.email "{GITHUB_EMAIL}"')
                        os.system(f'git config --global user.name "{GITHUB_USERNAME}"')
                        
                        # Remove each unused item
                        for item in items_to_remove:
                            try:
                                if not item.is_exported:  # Double check it's not exported
                                    item.remove()
                            except Exception as e:
                                print(f"Warning: Error removing item {item.name}: {str(e)}")
                                continue
                        
                        # Commit the changes
                        codebase.commit()
                        codebase.git_commit("chore: remove dead code")
                        
                        # Create PR
                        pr_title = "chore: remove dead code"
                        pr_body = create_pr_description(analysis_result['analysis'])
                        pr = codebase.create_pr(
                            title=pr_title,
                            body=pr_body
                        )
                        
                        # Add PR information to the response
                        analysis_result['pull_request'] = {
                            'url': pr.html_url if hasattr(pr, 'html_url') else None,
                            'number': pr.number if hasattr(pr, 'number') else None
                        }
                    
                    except Exception as e:
                        raise HTTPException(
                            status_code=500,
                            detail=f"Error creating pull request: {str(e)}"
                        )
                
                return analysis_result
                
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"Error analyzing repository: {str(e)}"
                )
            
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Server error: {str(e)}"
        )

@app.get("/")
async def root():
    """Root endpoint returning API information."""
    return {
        "name": "Dead Code Analyzer API",
        "version": "1.0.0",
        "description": "API to analyze GitHub repositories for dead code"
    } 