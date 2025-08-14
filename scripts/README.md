# GitHub Stats Generator

This script generates GitHub statistics for your profile README without depending on external actions or libraries.

## Features

- **Simple**: Single Python script that does everything
- **Secure**: No token leakage, all processing happens locally
- **Templated**: Updates your README.md from TEMPLATE.md with real GitHub stats
- **Automated**: Runs via GitHub Actions workflow

## How It Works

The script:
1. Fetches your GitHub statistics using the GitHub API
2. Extracts specific values for your template placeholders
3. Processes your TEMPLATE.md file
4. Generates README.md with the actual values
5. Saves data to JSON for reference

## Setup

### Prerequisites

- Python 3.9+
- `requests` library (installed automatically by the workflow)

### Environment Variables

The script requires:
- `GITHUB_TOKEN`: Your GitHub personal access token with `public_repo` scope
- `GITHUB_USERNAME`: Your GitHub username (optional, will auto-detect from git config)

## Usage

### Manual Execution

```bash
# From repository root
export GITHUB_TOKEN="your_token_here"
export GITHUB_USERNAME="your_username"  # optional
python scripts/github_stats.py TEMPLATE.md README.md
```

### GitHub Actions

The workflow in `.github/workflows/github-stats.yml`:
- Runs daily at midnight
- Runs on manual trigger
- Runs on pushes to main branch
- Automatically updates your README.md with fresh stats

## What Gets Generated

The script populates your TEMPLATE.md with actual GitHub statistics. For example, it will replace placeholders like:

```json
"Stats": {
    "Account Age": "{{ ACCOUNT_AGE }} years",
    "Pushed": "{{ COMMITS }} commits",
    "Received": "{{ STARS }} stars",
    "Own": "{{ REPOSITORIES }} repositories",
    "Contributed to": "{{ REPOSITORIES_CONTRIBUTED_TO }} public repositories",
}
```

With actual values:

```json
"Stats": {
    "Account Age": "5 years",
    "Pushed": "1024 commits",
    "Received": "156 stars",
    "Own": "42 repositories",
    "Contributed to": "18 public repositories",
}
```

It also populates repository-specific star counts for your highlighted projects.

## Customization

- Modify the `get_github_stats()` function to fetch additional statistics
- Add more template values to match your TEMPLATE.md placeholders
- Customize the JSON output format

## Troubleshooting

### Common Issues

1. **Token Permission Error**: Ensure your `GITHUB_TOKEN` has `public_repo` scope
2. **Rate Limiting**: GitHub API has rate limits; the script handles this gracefully
3. **Username Detection**: If auto-detection fails, explicitly set `GITHUB_USERNAME`
4. **Template Format**: Make sure your template uses the format `{{ PLACEHOLDER }}`

### Debug Output

The script provides verbose output. Check the GitHub Actions logs for detailed information.

## Benefits

✅ **Simple**: Single script with minimal dependencies
✅ **Secure**: No token leakage, all processing happens locally
✅ **Privacy**: No data sent to third-party services
✅ **Reliability**: No dependency on external actions
✅ **Customization**: Easy to modify for your specific template needs
✅ **Transparency**: Full visibility into what the script does

## Contributing

Feel free to submit issues or pull requests to improve this script!
