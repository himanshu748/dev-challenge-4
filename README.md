# PRReviewIQ

PRReviewIQ is a local FastAPI app plus Python CLI that reviews pull request diffs with Claude and logs every review insight into a Notion knowledge base through Notion MCP.

## What it does

- `POST /api/setup` provisions the Notion workspace structure.
- `POST /api/review-pr` reviews a raw git diff and logs findings.
- `POST /api/review-file` reviews a single file for pre-commit style checks.
- `GET /api/standards` returns the living coding standards database as JSON.
- `POST /api/weekly-digest` creates a weekly quality report page in Notion.
- `python review.py --repo /path/to/repo` runs the CLI against a local git repo.

## Important Notion MCP note

The prompt referenced Anthropic's remote MCP beta header `mcp-client-2025-04-04`, but that beta is deprecated as of March 10, 2026. This implementation uses the official `@notionhq/notion-mcp-server` package locally via `npx`, with `NOTION_TOKEN` passed to the MCP server, so all Notion writes still happen through MCP and never through direct REST calls from this app.

## Prerequisites

- Python 3.11+
- Node.js and `npx`
- A Notion integration token in `NOTION_TOKEN`
- A parent Notion page ID in `NOTION_PARENT_PAGE_ID`
- An Anthropic API key in `ANTHROPIC_API_KEY`

## Run locally

```bash
uvicorn app.main:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

## CLI examples

```bash
python review.py --repo /path/to/repo
python review.py --file path/to/file.py --pr-title "Pre-commit review" --repo-name my-repo
```

## Project layout

```text
app/
  api/
  core/
  schemas/
  services/
  static/
review.py
tests/
```
