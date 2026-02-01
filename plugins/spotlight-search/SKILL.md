---
name: spotlight-search
description: Search local files using macOS Spotlight (mdfind). Fast indexed search across PDFs, Office docs, and plain text. Use when user asks to find files by content ("search my documents for X"), locate documents on topics ("find my resume", "tax forms"), or needs to discover files without knowing exact path. Triggers on phrases like "search Downloads for", "find PDFs about", "locate documents containing".
allowed-tools: [Bash, Read]
user-invocable: true
---

# Spotlight Search (mdfind)

Fast file discovery using macOS Spotlight's pre-built index. Faster than grep/rg for broad searches.

## Dependencies

- **macOS** - Spotlight is macOS-only
- **pdftotext** (optional) - For extracting text from PDF results (`brew install poppler`)

## Core Patterns

### Simple Search (names + content)

```bash
mdfind "quarterly report"
```

### Search by Filename

```bash
mdfind -name "quarterly_report"          # Filename contains this string
mdfind -name ".pdf"                       # All PDFs by extension
```

### Scoped to Directory

```bash
mdfind -onlyin ~/Downloads "invoice 2024"
mdfind -onlyin ~ "project proposal"  # home directory
```

### Content-Specific Search

```bash
mdfind 'kMDItemTextContent == "*budget*"'
mdfind 'kMDItemTextContent CONTAINS[cd] "project status"'  # case-insensitive
```

### By File Type (standalone)

```bash
mdfind 'kind:pdf'
mdfind 'kind:word'                       # Word docs
mdfind 'kind:presentation'               # PowerPoint/Keynote
mdfind 'kind:spreadsheet'                # Excel/Numbers
```

### File Type + Content (use -interpret)

```bash
# The -interpret flag allows combining kind: with text search
mdfind -interpret 'kind:pdf budget'
mdfind -interpret 'kind:word meeting notes'
mdfind -onlyin ~/Downloads -interpret 'kind:pdf invoice'
```

### Combined Predicates (full syntax)

```bash
# Multiple content terms (AND)
mdfind 'kMDItemTextContent == "*invoice*" && kMDItemTextContent == "*2024*"'

# File type + content (use kMDItemContentType, NOT kind:)
mdfind 'kMDItemContentType == "com.adobe.pdf" && kMDItemTextContent == "*contract*"'

# Common content types:
#   com.adobe.pdf                    - PDF
#   com.microsoft.word.doc           - Word .doc
#   org.openxmlformats.wordprocessingml.document  - Word .docx
#   public.plain-text                - Plain text
#   public.html                      - HTML
```

### By Date

```bash
# Modified today
mdfind 'kMDItemFSContentChangeDate > $time.today'

# Modified in last 7 days
mdfind 'kMDItemFSContentChangeDate > $time.today(-7)'

# Created after specific date
mdfind 'kMDItemFSCreationDate > $time.iso(2026-01-01)'
```

## Example Output

```
$ mdfind -onlyin ~/Downloads "quarterly report"
/Users/me/Downloads/Q3 Quarterly Report.pdf
/Users/me/Downloads/quarterly-report-draft.docx
/Users/me/Downloads/Budget Notes.txt
```

## Limitations

**mdfind returns file paths only** - no content snippets or context around matches.

For context extraction, use a two-step approach:

```bash
# Step 1: Find files
# Step 2: Extract context with rg

# Plain text files
mdfind -onlyin ~/Downloads "project status" | xargs rg -C 3 "status"

# PDFs (requires pdftotext from poppler)
mdfind -interpret 'kind:pdf budget' | while read f; do
  echo "=== $f ==="
  pdftotext "$f" - 2>/dev/null | rg -C 2 -i "budget" || true
done
```

## Useful Metadata Keys

| Key | Description |
|-----|-------------|
| `kMDItemTextContent` | File contents (searchable text) |
| `kMDItemFSContentChangeDate` | Last modified date |
| `kMDItemFSCreationDate` | Creation date |
| `kMDItemContentType` | MIME type (e.g., `com.adobe.pdf`) |
| `kMDItemKind` | Human-readable type (e.g., "PDF Document") |
| `kMDItemDisplayName` | File name |

## Sorting Results

mdfind doesn't sort. To sort by date:

```bash
# Sort by last modified (most recent first)
mdfind -onlyin ~/Downloads "query" | while IFS= read -r f; do
  ts=$(mdls -raw -name kMDItemFSContentChangeDate "$f" 2>/dev/null)
  printf '%s\t%s\n' "$ts" "$f"
done | sort -r | cut -f2-
```

## Tips

1. **Exclude noise**: Pipe through `grep -v` to filter out unwanted paths

   ```bash
   mdfind "query" | grep -v "node_modules\|\.git\|Library/Caches"
   ```

2. **Limit results**: Use `head` for quick exploration

   ```bash
   mdfind "query" | head -20
   ```

3. **Check what's indexed**: Some folders may be excluded from Spotlight

   ```bash
   # System Preferences > Siri & Spotlight > Spotlight Privacy
   ```

4. **Force reindex** (if results seem stale):

   ```bash
   sudo mdutil -E /  # Rebuilds entire index - takes time
   ```

## Common Use Cases

### Find documents with multiple terms

```bash
mdfind -onlyin ~ 'kMDItemTextContent == "*invoice*" && kMDItemTextContent == "*2024*"'
```

### Find documents matching any of several terms

```bash
mdfind 'kMDItemTextContent == "*resume*" || kMDItemTextContent == "*CV*"'
```

### Find PDFs containing specific text

```bash
mdfind -interpret 'kind:pdf quarterly report'
# OR with full predicate:
mdfind 'kMDItemContentType == "com.adobe.pdf" && kMDItemTextContent == "*quarterly report*"'
```

### Find recently modified documents by topic

```bash
mdfind -onlyin ~/Documents 'kMDItemFSContentChangeDate > $time.today(-7) && kMDItemTextContent == "*meeting*"'
```
