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
    
    # Get repositories contributed to using the events API
    print("Fetching repositories contributed to...")
    events_url = f'https://api.github.com/users/{username}/events/public?per_page=100'
    events_response = requests.get(events_url, headers=headers)
    events_data = events_response.json()
    
    # Get user's events to find contributed repos
    contributed_repos = set()
    if isinstance(events_data, list):
        for event in events_data:
            # PushEvent, PullRequestEvent, IssuesEvent, etc. indicate contribution
            repo_name = event.get('repo', {}).get('name', '')
            if '/' in repo_name:
                owner, name = repo_name.split('/', 1)
                if owner.lower() != username.lower():  # Not user's own repo
                    contributed_repos.add(repo_name)
    
    # Also check starred repositories for additional contributions
    starred_url = f'https://api.github.com/users/{username}/starred?per_page=100'
    starred_response = requests.get(starred_url, headers=headers)
    starred_data = starred_response.json()
    
    if isinstance(starred_data, list):
        for repo in starred_data:
            # Check if user has contributed to this repo
            repo_full_name = repo.get('full_name', '')
            if repo_full_name and repo.get('owner', {}).get('login') != username:
                # Check for user's contributions to this repo
                contributors_url = f'https://api.github.com/repos/{repo_full_name}/contributors'
                try:
                    contributors_response = requests.get(contributors_url, headers=headers)
                    contributors_data = contributors_response.json()
                    if isinstance(contributors_data, list):
                        for contributor in contributors_data:
                            if contributor.get('login') == username:
                                contributed_repos.add(repo_full_name)
                                break
                except:
                    # Skip if API rate limit or other issues
                    pass
    
    # Get commit count using contribution stats API (more accurate)
    print("Calculating commit count...")
    total_commits = 0
    
    # Get the user's contribution stats
    stats_url = f'https://api.github.com/users/{username}/repos?per_page=100'
    stats_response = requests.get(stats_url, headers=headers)
    stats_data = stats_response.json()
    
    if isinstance(stats_data, list):
        # Process each repository
        for repo in stats_data:
            repo_name = repo.get('name')
            repo_full_name = repo.get('full_name')
            
            # Get commit stats for this repository
            try:
                # Use statistics API for more accurate counts
                commit_activity_url = f'https://api.github.com/repos/{repo_full_name}/stats/contributors'
                commit_response = requests.get(commit_activity_url, headers=headers)
                commit_data = commit_response.json()
                
                if isinstance(commit_data, list):
                    for contributor in commit_data:
                        if contributor.get('author', {}).get('login') == username:
                            # Sum up all commits from this contributor
                            total_commits += contributor.get('total', 0)
                            break
                else:
                    # Fallback to direct commit counting
                    commits_url = f'https://api.github.com/repos/{repo_full_name}/commits?author={username}&per_page=1'
                    commits_response = requests.get(commits_url, headers=headers)
                    
                    # Check if we have the last page info in headers
                    if 'link' in commits_response.headers:
                        link_header = commits_response.headers['link']
                        # Extract the last page number from the Link header
                        last_page_match = re.search(r'page=(\d+)>; rel="last"', link_header)
                        if last_page_match:
                            last_page = int(last_page_match.group(1))
                            # Get actual count from last page
                            repo_commits = last_page
                            total_commits += repo_commits
            except Exception as e:
                # If API fails, skip this repo
                print(f"Error getting commits for {repo_full_name}: {e}")
                pass
    
    # If total commits is still suspiciously high (over 50,000), use a more conservative estimate
    if total_commits > 50000:
        print("Commit count seems high, using profile contribution data for estimation...")
        # Use user profile data which is more reliable but less detailed
        user_url = f'https://api.github.com/users/{username}'
        user_response = requests.get(user_url, headers=headers)
        user_data = user_response.json()
        
        # Get public contributions from profile
        public_contributions = user_data.get('public_repos', 0) * 10  # Rough estimate
        
        # Use the lower of the two estimates
        total_commits = min(total_commits, public_contributions)
    
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
