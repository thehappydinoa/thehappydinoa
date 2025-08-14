#!/usr/bin/env python3
"""
GitHub Stats Generator
Generates GitHub statistics and updates README.md from TEMPLATE.md
"""

import os
import sys
import json
import requests
from datetime import datetime
import re

def get_github_stats(username, token):
    """Fetch GitHub statistics using GitHub API"""
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    
    print(f"Fetching stats for user: {username}")
    
    # Get user info
    user_url = f'https://api.github.com/users/{username}'
    user_response = requests.get(user_url, headers=headers)
    user_data = user_response.json()
    
    # Get repositories
    repos_url = f'https://api.github.com/users/{username}/repos?per_page=100&sort=updated'
    repos_response = requests.get(repos_url, headers=headers)
    repos_data = repos_response.json()
    
    # Get specific repository stats for template values
    acq_stars = 0
    irb_stars = 0
    rootos_stars = 0
    tplink_stars = 0
    
    for repo in repos_data:
        repo_name = repo.get('name', '').lower()
        stars = repo.get('stargazers_count', 0)
        
        if 'awesome-censys-queries' in repo_name:
            acq_stars = stars
        elif 'iosrestrictionbruteforce' in repo_name:
            irb_stars = stars
        elif 'rootos' in repo_name:
            rootos_stars = stars
        elif 'tp-link-defaults' in repo_name or 'tplink' in repo_name:
            tplink_stars = stars
    
    # Calculate account age
    created_at = user_data.get('created_at')
    account_age = 0
    if created_at:
        created_date = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        account_age = (datetime.now(created_date.tzinfo) - created_date).days // 365
    
    # Calculate stats
    total_repos = len(repos_data)
    total_stars = sum(repo.get('stargazers_count', 0) for repo in repos_data)
    
    # Get repositories contributed to
    print("Fetching repositories contributed to...")
    contributed_repos_url = f'https://api.github.com/users/{username}/repos?per_page=100&type=all&sort=updated'
    contributed_response = requests.get(contributed_repos_url, headers=headers)
    contributed_data = contributed_response.json()
    
    # Count unique repositories contributed to (excluding own repos)
    contributed_repos = set()
    for repo in contributed_data:
        if repo.get('fork') and not repo.get('owner', {}).get('login') == username:
            contributed_repos.add(repo.get('name'))
    
    # Get commit count (approximate)
    print("Calculating commit count...")
    total_commits = 0
    
    # We'll check the commit count for each repository owned by the user
    for repo in repos_data:
        repo_name = repo.get('name')
        repo_owner = repo.get('owner', {}).get('login')
        
        if repo_owner == username:
            # Get commit count for this repository
            commits_url = f'https://api.github.com/repos/{username}/{repo_name}/commits?per_page=1&author={username}'
            commits_response = requests.get(commits_url, headers=headers)
            
            # Check if we have the last page info in headers
            if 'link' in commits_response.headers:
                link_header = commits_response.headers['link']
                # Extract the last page number from the Link header
                last_page_match = re.search(r'page=(\d+)>; rel="last"', link_header)
                if last_page_match:
                    last_page = int(last_page_match.group(1))
                    # GitHub API paginates with 100 items per page
                    repo_commits = last_page * 100
                    total_commits += repo_commits
            else:
                # If no pagination, count commits directly
                try:
                    # Try to get all commits for small repos
                    all_commits_url = f'https://api.github.com/repos/{username}/{repo_name}/commits?author={username}&per_page=100'
                    all_commits_response = requests.get(all_commits_url, headers=headers)
                    all_commits_data = all_commits_response.json()
                    if isinstance(all_commits_data, list):
                        total_commits += len(all_commits_data)
                except:
                    # If that fails, estimate
                    total_commits += 1
    
    # Template values for TEMPLATE.md
    template_values = {
        'ACQ_STARS': acq_stars,
        'IRB_STARS': irb_stars,
        'ROOTOS_STARS': rootos_stars,
        'TPLINK_STARS': tplink_stars,
        'ACCOUNT_AGE': account_age,
        'COMMITS': total_commits,
        'STARS': total_stars,
        'REPOSITORIES': total_repos,
        'REPOSITORIES_CONTRIBUTED_TO': len(contributed_repos)
    }
    
    print(f"Retrieved stats: {total_repos} repos, {total_stars} stars, {total_commits} commits, {len(contributed_repos)} contributed repos")
    return template_values

def process_template(template_path, output_path, template_values):
    """Process template file and replace template values with stats data"""
    
    # Read template file
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            template_content = f.read()
    except FileNotFoundError:
        print(f"Error: Template file {template_path} not found.")
        return False
    
    # Replace template values
    processed_content = template_content
    for key, value in template_values.items():
        placeholder = f"{{{{ {key} }}}}"
        processed_content = processed_content.replace(placeholder, str(value))
    
    # Write processed content
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(processed_content)
        print(f"Processed template saved to {output_path}")
        return True
    except Exception as e:
        print(f"Error writing to {output_path}: {e}")
        return False

def save_stats_to_json(stats, output_path='github_stats.json'):
    """Save stats to JSON file"""
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)
        print(f"Stats saved to {output_path}")
        return True
    except Exception as e:
        print(f"Error saving to {output_path}: {e}")
        return False

def main():
    """Main function"""
    # Parse command line arguments
    template_path = 'TEMPLATE.md'
    output_path = 'README.md'
    
    # Override with command line args if provided
    if len(sys.argv) > 1:
        template_path = sys.argv[1]
    if len(sys.argv) > 2:
        output_path = sys.argv[2]
    
    # Get GitHub token from environment
    token = os.environ.get('GITHUB_TOKEN')
    if not token:
        print("Error: GITHUB_TOKEN environment variable not set")
        sys.exit(1)
    
    # Get username from environment or default to repository owner
    username = os.environ.get('GITHUB_USERNAME')
    if not username:
        # Try to get from repository
        try:
            with open('.git/config', 'r') as f:
                config = f.read()
                if 'github.com:' in config:
                    # Extract username from git remote
                    match = re.search(r'github\.com:([^/]+)/', config)
                    if match:
                        username = match.group(1)
        except:
            pass
        
        if not username:
            print("Error: GITHUB_USERNAME environment variable not set and could not determine from git config")
            sys.exit(1)
    
    try:
        # Get stats
        template_values = get_github_stats(username, token)
        
        # Print template values
        print("\nTemplate values for TEMPLATE.md:")
        for key, value in template_values.items():
            print(f"  {key}: {value}")
        
        # Save to JSON file
        save_stats_to_json(template_values)
        
        # Process template
        print(f"\nProcessing template: {template_path}")
        print(f"Output to: {output_path}")
        if process_template(template_path, output_path, template_values):
            print("Template processing completed successfully!")
        else:
            print("Template processing failed!")
            sys.exit(1)
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
