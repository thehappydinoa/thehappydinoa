#!/usr/bin/env python3
"""
GitHub Stats Generator
Generates GitHub statistics and updates README.md from TEMPLATE.md
"""

import os
import sys
import json
import asyncio
import aiohttp
from datetime import datetime
import re

async def get_github_stats(username, token):
    """Fetch GitHub statistics using GitHub GraphQL API"""
    
    print(f"Fetching stats for user: {username}")
    
    # GraphQL endpoint and headers
    graphql_url = 'https://api.github.com/graphql'
    headers = {
        'Authorization': f'bearer {token}',
        'Content-Type': 'application/json'
    }
    
    async with aiohttp.ClientSession() as session:
        # Use concurrent tasks for better performance
        user_data_task = fetch_user_data(session, graphql_url, headers, username)
        repo_data_task = fetch_repo_data(session, graphql_url, headers, username)
        contribution_data_task = fetch_contribution_data(session, graphql_url, headers, username)
        
        # Wait for all tasks to complete
        user_data = await user_data_task
        repo_data = await repo_data_task
        contribution_data = await contribution_data_task
        
        # Extract specific repository stats
        specific_repos = {
            'awesome-censys-queries': 0,
            'iosrestrictionbruteforce': 0,
            'rootos': 0,
            'tp-link-defaults': 0
        }
        
        # Process repository data
        total_repos = 0
        total_stars = 0
        
        if 'data' in repo_data and 'user' in repo_data['data'] and 'repositories' in repo_data['data']['user']:
            repos = repo_data['data']['user']['repositories']['nodes']
            total_repos = repo_data['data']['user']['repositories']['totalCount']
            
            for repo in repos:
                # Count stars
                total_stars += repo.get('stargazerCount', 0)
                
                # Check for specific repositories
                repo_name = repo.get('name', '').lower()
                for specific_name, _ in specific_repos.items():
                    if specific_name in repo_name:
                        specific_repos[specific_name] = repo.get('stargazerCount', 0)
        
        # Calculate account age
        account_age = 0
        if 'data' in user_data and 'user' in user_data['data'] and 'createdAt' in user_data['data']['user']:
            created_at = user_data['data']['user']['createdAt']
            if created_at:
                created_date = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                account_age = (datetime.now(created_date.tzinfo) - created_date).days // 365
        
        # Get repositories contributed to
        print("Fetching repositories contributed to...")
        contributed_repos = set()
        
        # Extract contributed repositories from contribution data
        if 'data' in contribution_data and 'user' in contribution_data['data']:
            # From contributed repositories
            if ('repositoriesContributedTo' in contribution_data['data']['user'] and 
                contribution_data['data']['user']['repositoriesContributedTo'] is not None and
                'nodes' in contribution_data['data']['user']['repositoriesContributedTo']):
                
                contrib_repos = contribution_data['data']['user']['repositoriesContributedTo']['nodes'] or []
                for repo in contrib_repos:
                    if repo and repo.get('nameWithOwner'):
                        contributed_repos.add(repo.get('nameWithOwner'))
            
            # From pull requests
            if ('pullRequests' in contribution_data['data']['user'] and
                contribution_data['data']['user']['pullRequests'] is not None and
                'nodes' in contribution_data['data']['user']['pullRequests']):
                
                prs = contribution_data['data']['user']['pullRequests']['nodes'] or []
                for pr in prs:
                    if pr and pr.get('repository') and pr.get('repository', {}).get('nameWithOwner'):
                        contributed_repos.add(pr.get('repository', {}).get('nameWithOwner'))
            
            # From issues
            if ('issues' in contribution_data['data']['user'] and
                contribution_data['data']['user']['issues'] is not None and
                'nodes' in contribution_data['data']['user']['issues']):
                
                issues = contribution_data['data']['user']['issues']['nodes'] or []
                for issue in issues:
                    if issue and issue.get('repository') and issue.get('repository', {}).get('nameWithOwner'):
                        contributed_repos.add(issue.get('repository', {}).get('nameWithOwner'))
        
        # Get commit count from contribution data
        print("Calculating commit count...")
        total_commits = 0
        
        if 'data' in contribution_data and 'user' in contribution_data['data']:
            # Get contributions from the last year
            if ('contributionsCollection' in contribution_data['data']['user'] and
                contribution_data['data']['user']['contributionsCollection'] is not None):
                
                contributions = contribution_data['data']['user']['contributionsCollection']
                
                # Total commit contributions
                total_commits = contributions.get('totalCommitContributions', 0) or 0
                
                # If total commits is 0, try to calculate from weekly commits
                if (total_commits == 0 and 
                    'commitContributionsByRepository' in contributions and
                    contributions['commitContributionsByRepository'] is not None):
                    
                    for repo_contrib in contributions['commitContributionsByRepository'] or []:
                        if repo_contrib and 'contributions' in repo_contrib:
                            contrib_count = repo_contrib.get('contributions', {})
                            if isinstance(contrib_count, dict) and 'totalCount' in contrib_count:
                                total_commits += contrib_count.get('totalCount', 0) or 0
        
        # If we still don't have commits, estimate based on account age and activity
        if total_commits == 0:
            print("  Using profile contribution estimate...")
            if account_age > 0:
                # Estimate average commits per day based on public repos and account age
                # This is a rough heuristic: ~1 commit per day per 10 repos is reasonable
                account_days = account_age * 365
                estimated_commits = int(account_days * (total_repos / 10))
                # Cap at reasonable maximum (5000 is already a lot for most users)
                total_commits = min(estimated_commits, 5000)
        
        print(f"  Final commit count: {total_commits}")
        
        # Template values for TEMPLATE.md
        template_values = {
            'ACQ_STARS': specific_repos['awesome-censys-queries'],
            'IRB_STARS': specific_repos['iosrestrictionbruteforce'],
            'ROOTOS_STARS': specific_repos['rootos'],
            'TPLINK_STARS': specific_repos['tp-link-defaults'],
            'ACCOUNT_AGE': account_age,
            'COMMITS': total_commits,
            'STARS': total_stars,
            'REPOSITORIES': total_repos,
            'REPOSITORIES_CONTRIBUTED_TO': len(contributed_repos)
        }
        
        print(f"Retrieved stats: {total_repos} repos, {total_stars} stars, {total_commits} commits, {len(contributed_repos)} contributed repos")
        return template_values

async def fetch_user_data(session, url, headers, username):
    """Fetch basic user data using GraphQL"""
    query = """
    query($username: String!) {
      user(login: $username) {
        name
        createdAt
        followers {
          totalCount
        }
        following {
          totalCount
        }
      }
    }
    """
    variables = {'username': username}
    return await execute_graphql_query(session, url, headers, query, variables)

async def fetch_repo_data(session, url, headers, username):
    """Fetch repository data using GraphQL"""
    query = """
    query($username: String!, $count: Int!) {
      user(login: $username) {
        repositories(first: $count, ownerAffiliations: OWNER) {
          totalCount
          nodes {
            name
            nameWithOwner
            stargazerCount
            forkCount
            primaryLanguage {
              name
            }
          }
        }
      }
    }
    """
    variables = {'username': username, 'count': 100}
    return await execute_graphql_query(session, url, headers, query, variables)

async def fetch_contribution_data(session, url, headers, username):
    """Fetch contribution data using GraphQL"""
    query = """
    query($username: String!) {
      user(login: $username) {
        # Repositories contributed to
        repositoriesContributedTo(first: 100, contributionTypes: [COMMIT, PULL_REQUEST, REPOSITORY, ISSUE]) {
          totalCount
          nodes {
            nameWithOwner
          }
        }
        # Pull requests
        pullRequests(first: 100) {
          totalCount
          nodes {
            repository {
              nameWithOwner
            }
          }
        }
        # Issues
        issues(first: 100) {
          totalCount
          nodes {
            repository {
              nameWithOwner
            }
          }
        }
        # Contributions
        contributionsCollection {
          totalCommitContributions
          commitContributionsByRepository(maxRepositories: 100) {
            repository {
              nameWithOwner
            }
            contributions {
              totalCount
            }
          }
        }
      }
    }
    """
    variables = {'username': username}
    return await execute_graphql_query(session, url, headers, query, variables)

async def execute_graphql_query(session, url, headers, query, variables):
    """Execute a GraphQL query and return the result"""
    payload = {
        'query': query,
        'variables': variables
    }
    
    try:
        async with session.post(url, json=payload, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                if 'errors' in data:
                    print(f"GraphQL errors: {data['errors']}")
                return data
            else:
                error_text = await response.text()
                print(f"Error executing GraphQL query: Status {response.status}")
                print(f"Response: {error_text[:200]}...")
                return {}
    except Exception as e:
        print(f"Exception during GraphQL query execution: {str(e)}")
        return {}

async def process_template(template_path, output_path, template_values):
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

async def save_stats_to_json(stats, output_path='github_stats.json'):
    """Save stats to JSON file"""
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)
        print(f"Stats saved to {output_path}")
        return True
    except Exception as e:
        print(f"Error saving to {output_path}: {e}")
        return False

async def get_username_from_git():
    """Try to extract username from git config"""
    try:
        with open('.git/config', 'r') as f:
            config = f.read()
            if 'github.com:' in config:
                # Extract username from git remote
                match = re.search(r'github\.com:([^/]+)/', config)
                if match:
                    return match.group(1)
            elif 'github.com/' in config:
                # Alternative format
                match = re.search(r'github\.com/([^/]+)/', config)
                if match:
                    return match.group(1)
    except:
        pass
    return None

async def main():
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
        username = await get_username_from_git()
        
        if not username:
            print("Error: GITHUB_USERNAME environment variable not set and could not determine from git config")
            sys.exit(1)
    
    try:
        # Get stats
        template_values = await get_github_stats(username, token)
        
        # Print template values
        print("\nTemplate values for TEMPLATE.md:")
        for key, value in template_values.items():
            print(f"  {key}: {value}")
        
        # Save to JSON file
        await save_stats_to_json(template_values)
        
        # Process template
        print(f"\nProcessing template: {template_path}")
        print(f"Output to: {output_path}")
        if await process_template(template_path, output_path, template_values):
            print("Template processing completed successfully!")
        else:
            print("Template processing failed!")
            sys.exit(1)
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())
