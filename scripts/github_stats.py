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
    
    # REST API headers (reused in multiple places)
    rest_headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    
    # Initialize stats containers
    specific_repos = {
        'awesome-censys-queries': 0,
        'iosrestrictionbruteforce': 0,
        'rootos': 0,
        'tp-link-defaults': 0
    }
    total_repos = 0
    total_stars = 0
    account_age = 0
    contributed_repos = set()
    total_commits = 0
    
    # Use a single ClientSession for all requests
    async with aiohttp.ClientSession() as session:
        # Fetch data concurrently for better performance
        user_data_task = fetch_user_data(session, graphql_url, headers, username)
        repo_data_task = fetch_repo_data(session, graphql_url, headers, username)
        contribution_data_task = fetch_contribution_data(session, graphql_url, headers, username)
        
        # Wait for all tasks to complete
        user_data = await user_data_task
        repo_data = await repo_data_task
        contribution_data = await contribution_data_task
        
        # Extract data from GraphQL responses
        user_data_obj = get_nested_value(user_data, ['data', 'user'], {})
        repo_data_obj = get_nested_value(repo_data, ['data', 'user', 'repositories'], {})
        contribution_data_obj = get_nested_value(contribution_data, ['data', 'user'], {})
        
        # Process repository data
        repos = get_nested_value(repo_data_obj, ['nodes'], [])
        total_repos = get_nested_value(repo_data_obj, ['totalCount'], 0)
        
        # Process repositories
        print("Checking repositories for specific projects:")
        for repo in repos:
            if repo is None:
                continue
                
            # Count stars
            stars = repo.get('stargazerCount', 0) or 0
            total_stars += stars
            
            # Check for specific repositories with better matching
            repo_name = repo.get('name', '').lower()
            full_name = repo.get('nameWithOwner', '').lower()
            
            # Print repository info for debugging
            print(f"  Repository: {full_name}, Stars: {stars}")
            
            # Check for specific repositories of interest
            await check_specific_repo(repo_name, full_name, stars, specific_repos)
        
        # Calculate account age
        created_at = user_data_obj.get('createdAt')
        if created_at:
            try:
                created_date = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                account_age = max(1, (datetime.now(created_date.tzinfo) - created_date).days // 365)
            except Exception as e:
                print(f"Error calculating account age: {e}")
                account_age = 1  # Default to 1 year if calculation fails
        
        # Get repositories contributed to
        print("Fetching repositories contributed to...")
        contributed_repos = await get_contributed_repos(session, username, token, contribution_data_obj)
        
        # Get commit count
        print("Calculating commit count...")
        total_commits = await get_commit_count(contribution_data_obj, account_age, total_repos)
        
        # Check for missing specific repositories and apply fallbacks
        await apply_repo_fallbacks(session, specific_repos, rest_headers)
        
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

def get_nested_value(data, path, default=None):
    """Safely get a nested value from a dictionary using a path list"""
    current = data
    for key in path:
        if not isinstance(current, dict) or key not in current or current[key] is None:
            return default
        current = current[key]
    return current or default

async def check_specific_repo(repo_name, full_name, stars, specific_repos):
    """Check if a repository matches any of the specific repositories we're looking for"""
    # Exact match for awesome-censys-queries
    if repo_name == 'awesome-censys-queries' or 'thehappydinoa/awesome-censys-queries' in full_name:
        specific_repos['awesome-censys-queries'] = stars
        print(f"    ✓ Found awesome-censys-queries: {stars} stars")
    
    # Match for iOSRestrictionBruteForce (case insensitive)
    elif repo_name == 'iosrestrictionbruteforce' or 'iosrestrictionbruteforce' in full_name:
        specific_repos['iosrestrictionbruteforce'] = stars
        print(f"    ✓ Found iOSRestrictionBruteForce: {stars} stars")
    
    # Match for rootOS
    elif repo_name == 'rootos' or 'rootos' in full_name:
        specific_repos['rootos'] = stars
        print(f"    ✓ Found rootOS: {stars} stars")
    
    # Match for TP-Link-defaults
    elif repo_name == 'tp-link-defaults' or 'tp-link-defaults' in full_name:
        specific_repos['tp-link-defaults'] = stars
        print(f"    ✓ Found TP-Link-defaults: {stars} stars")

async def get_contributed_repos(session, username, token, user_data):
    """Get repositories contributed to from GraphQL data or REST API fallback"""
    contributed_repos = set()
    
    # REST API headers
    rest_headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    
    # Try multiple methods to get contributed repositories, in order of preference
    methods = [
        extract_graphql_contributions,
        get_contributions_from_events,
        get_contributions_from_starred,
        get_contributions_from_activity
    ]
    
    for method in methods:
        # Skip if we already have some results
        if len(contributed_repos) > 0:
            break
            
        try:
            # Call the method and update our set
            new_repos = await method(session, username, rest_headers, user_data)
            contributed_repos.update(new_repos)
            
            # If we found some, report and continue
            if len(new_repos) > 0:
                method_name = method.__name__.replace('_', ' ').replace('get contributions from ', '')
                print(f"  Found {len(new_repos)} contributed repos via {method_name}")
        except Exception as e:
            print(f"  Error in {method.__name__}: {e}")
    
    # If all methods failed, log it but return the empty set
    if len(contributed_repos) == 0:
        print("  Could not find any contributed repositories through any method")
    
    return contributed_repos

async def extract_graphql_contributions(session, username, headers, user_data):
    """Extract contributed repositories from GraphQL data"""
    contributed_repos = set()
    
    # Direct contributions
    repos_data = get_nested_value(user_data, ['repositoriesContributedTo'], {})
    for repo in get_nested_value(repos_data, ['nodes'], []):
        if repo and repo.get('nameWithOwner'):
            contributed_repos.add(repo.get('nameWithOwner'))
    
    # Pull requests
    pr_data = get_nested_value(user_data, ['pullRequests'], {})
    for pr in get_nested_value(pr_data, ['nodes'], []):
        repo = get_nested_value(pr, ['repository'], {})
        if repo and repo.get('nameWithOwner'):
            contributed_repos.add(repo.get('nameWithOwner'))
    
    # Issues
    issues_data = get_nested_value(user_data, ['issues'], {})
    for issue in get_nested_value(issues_data, ['nodes'], []):
        repo = get_nested_value(issue, ['repository'], {})
        if repo and repo.get('nameWithOwner'):
            contributed_repos.add(repo.get('nameWithOwner'))
            
    return contributed_repos

async def get_contributions_from_events(session, username, headers, *args):
    """Get contributed repositories from user's public events"""
    contributed_repos = set()
    
    # Use REST API to get events
    events_url = f'https://api.github.com/users/{username}/events/public'
    async with session.get(events_url, headers=headers) as response:
        if response.status == 200:
            events_data = await response.json()
            
            # Process events to find contributed repositories
            for event in events_data:
                repo = get_nested_value(event, ['repo', 'name'])
                if repo and not repo.startswith(f"{username}/"):
                    contributed_repos.add(repo)
    
    return contributed_repos

async def get_contributions_from_starred(session, username, headers, *args):
    """Get potential contributed repositories from starred repositories"""
    contributed_repos = set()
    
    # Get starred repositories
    starred_url = f'https://api.github.com/users/{username}/starred'
    async with session.get(starred_url, headers=headers) as response:
        if response.status == 200:
            starred_data = await response.json()
            
            # Add starred repos that aren't owned by the user
            for repo in starred_data:
                full_name = repo.get('full_name')
                owner = get_nested_value(repo, ['owner', 'login'])
                if full_name and owner and owner.lower() != username.lower():
                    contributed_repos.add(full_name)
    
    return contributed_repos

async def get_contributions_from_activity(session, username, headers, *args):
    """Get potential contributed repositories from user activity feed"""
    contributed_repos = set()
    
    # Get received events (activity where others have mentioned the user)
    activity_url = f'https://api.github.com/users/{username}/received_events'
    async with session.get(activity_url, headers=headers) as response:
        if response.status == 200:
            activity_data = await response.json()
            
            # Process activity to find repositories
            for event in activity_data:
                repo = get_nested_value(event, ['repo', 'name'])
                if repo and not repo.startswith(f"{username}/"):
                    contributed_repos.add(repo)
    
    return contributed_repos

async def apply_repo_fallbacks(session, specific_repos, headers):
    """Apply fallbacks for any missing specific repositories using direct API calls"""
    # Define repository mappings with their API endpoints and keys
    repo_fallbacks = [
        {
            'key': 'awesome-censys-queries',
            'endpoint': 'https://api.github.com/repos/thehappydinoa/awesome-censys-queries',
            'display_name': 'awesome-censys-queries'
        },
        {
            'key': 'iosrestrictionbruteforce',
            'endpoint': 'https://api.github.com/repos/thehappydinoa/iosrestrictionbruteforce',
            'display_name': 'iOSRestrictionBruteForce'
        },
        {
            'key': 'rootos',
            'endpoint': 'https://api.github.com/repos/thehappydinoa/rootos',
            'display_name': 'rootOS'
        },
        {
            'key': 'tp-link-defaults',
            'endpoint': 'https://api.github.com/repos/thehappydinoa/tp-link-defaults',
            'display_name': 'TP-Link-defaults'
        }
    ]
    
    # Check each repository and apply fallback if needed
    for repo in repo_fallbacks:
        if specific_repos[repo['key']] == 0:
            print(f"  Trying direct API call for {repo['display_name']}...")
            try:
                # Make the API request
                async with session.get(repo['endpoint'], headers=headers) as response:
                    if response.status == 200:
                        repo_data = await response.json()
                        stars = repo_data.get('stargazers_count', 0) or 0
                        specific_repos[repo['key']] = stars
                        print(f"    ✓ Found {repo['display_name']} via direct API: {stars} stars")
                    elif response.status == 404:
                        print(f"    Repository {repo['display_name']} not found (404)")
                    else:
                        print(f"    Error fetching {repo['display_name']}: HTTP {response.status}")
                        # Try alternative approach - search for the repository
                        await search_for_repo(session, repo['key'], repo['display_name'], specific_repos, headers)
            except Exception as e:
                print(f"    Error getting {repo['display_name']}: {e}")
                # Try alternative approach as fallback
                await search_for_repo(session, repo['key'], repo['display_name'], specific_repos, headers)

async def search_for_repo(session, repo_key, display_name, specific_repos, headers):
    """Search for a repository as a fallback method"""
    try:
        print(f"    Attempting to search for {display_name}...")
        search_query = f"q=repo:thehappydinoa/{repo_key}"
        search_url = f"https://api.github.com/search/repositories?{search_query}"
        
        async with session.get(search_url, headers=headers) as response:
            if response.status == 200:
                search_data = await response.json()
                items = search_data.get('items', [])
                if items and len(items) > 0:
                    stars = items[0].get('stargazers_count', 0) or 0
                    specific_repos[repo_key] = stars
                    print(f"    ✓ Found {display_name} via search: {stars} stars")
                else:
                    print(f"    No results found for {display_name} in search")
            else:
                print(f"    Search for {display_name} failed: HTTP {response.status}")
    except Exception as e:
        print(f"    Error searching for {display_name}: {e}")

async def get_commit_count(user_data, account_age, total_repos):
    """Calculate commit count from contribution data or estimate if not available"""
    # Try multiple methods to get commit count, in order of reliability
    methods = [
        get_commits_from_total_contributions,
        get_commits_from_repository_contributions,
        estimate_commits_from_profile
    ]
    
    # Pass context data to all methods
    context = {
        'user_data': user_data,
        'account_age': account_age,
        'total_repos': total_repos
    }
    
    # Try each method in order until one succeeds
    for method in methods:
        try:
            commits = await method(context)
            if commits > 0:
                method_name = method.__name__.replace('_', ' ').replace('get commits from ', '').replace('estimate commits from ', '')
                print(f"  Found {commits} commits via {method_name}")
                return commits
        except Exception as e:
            print(f"  Error in {method.__name__}: {e}")
    
    # If all methods failed, return a safe default
    print("  Could not determine commit count through any method, using default")
    return 100  # Safe default

async def get_commits_from_total_contributions(context):
    """Get commit count from totalCommitContributions field"""
    user_data = context['user_data']
    contributions = get_nested_value(user_data, ['contributionsCollection'], {})
    
    # Get total commit contributions (most reliable)
    total_commits = contributions.get('totalCommitContributions', 0) or 0
    if total_commits > 0:
        return total_commits
    
    # If zero, this method failed
    raise ValueError("No commit contributions found")

async def get_commits_from_repository_contributions(context):
    """Get commit count by summing repository contributions"""
    user_data = context['user_data']
    contributions = get_nested_value(user_data, ['contributionsCollection'], {})
    
    # Sum commits by repository
    repo_commits = 0
    for repo_contrib in get_nested_value(contributions, ['commitContributionsByRepository'], []):
        contrib_count = get_nested_value(repo_contrib, ['contributions', 'totalCount'], 0)
        repo_commits += contrib_count
    
    if repo_commits > 0:
        return repo_commits
    
    # If zero, this method failed
    raise ValueError("No repository commit contributions found")

async def estimate_commits_from_profile(context):
    """Estimate commit count based on account age and repository count"""
    account_age = context['account_age']
    total_repos = context['total_repos']
    
    if account_age <= 0 or total_repos <= 0:
        raise ValueError("Insufficient data for estimation")
    
    # Estimate average commits per day based on public repos and account age
    # This is a rough heuristic: ~1 commit per day per 10 repos is reasonable
    account_days = account_age * 365
    estimated_commits = int(account_days * (total_repos / 10))
    
    # Cap at reasonable maximum (5000 is already a lot for most users)
    return min(estimated_commits, 5000)

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
    # Split into two separate queries to avoid permissions issues
    
    # First query: Basic contribution data
    basic_query = """
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
        # Basic contribution stats
        contributionsCollection {
          totalCommitContributions
        }
      }
    }
    """
    
    # Second query: Try to get commit counts if permissions allow
    commit_query = """
    query($username: String!) {
      user(login: $username) {
        # Contributions by repository (may be restricted by some orgs)
        contributionsCollection {
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
    
    # Execute the basic query first
    variables = {'username': username}
    basic_data = await execute_graphql_query(session, url, headers, basic_query, variables)
    
    # Try the commit query, but don't fail if it doesn't work
    try:
        commit_data = await execute_graphql_query(session, url, headers, commit_query, variables)
        
        # If successful, merge the commit data into the basic data
        if ('data' in commit_data and 'user' in commit_data['data'] and 
            commit_data['data']['user'] is not None and 
            'contributionsCollection' in commit_data['data']['user']):
            
            # Ensure the structure exists in basic_data
            if 'data' in basic_data and 'user' in basic_data['data'] and basic_data['data']['user'] is not None:
                if 'contributionsCollection' not in basic_data['data']['user']:
                    basic_data['data']['user']['contributionsCollection'] = {}
                
                # Add the commit contributions by repository
                basic_data['data']['user']['contributionsCollection']['commitContributionsByRepository'] = (
                    commit_data['data']['user']['contributionsCollection'].get('commitContributionsByRepository')
                )
    except Exception as e:
        print(f"Warning: Could not fetch detailed commit data: {e}")
        # Continue with basic data only
    
    return basic_data

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
