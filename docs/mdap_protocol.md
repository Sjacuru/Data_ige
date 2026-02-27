# Stage 1 Discovery - Testing Checklist

## Pre-Test Setup

- [x]  Virtual environment activated
- [x]  All dependencies installed (`pip install -r requirements.txt`)
- [x]  `.env` file configured with correct URLs
- [x]  Chrome browser installed
- [x]  Internet connection active

## Manual Testing Steps

### 1. Run Discovery (Visible Browser)

```bash
python application/main.py
```

**Expected Results:**

- [x]  Browser opens and navigates to ContasRio -
- [x]  Companies are collected from table
- [x]  For each company, hierarchy is navigated
- [x]  Processo links are collected
- [x]  Browser closes automatically
- [x]  No crashes or unhandled exceptions

**Check Console Output:**

- [x]  Clear progress messages displayed
- [x]  Company names shown
- [x]  Processo counts displayed
- [ ]  Final summary shows totals

### 2. Run Discovery (Headless Mode)

```bash
python application/main.py --headless
```

**Expected Results:**

- [ ]  Runs without opening visible browser
- [ ]  Completes successfully
- [ ]  Same results as visible mode

### 3. Verify Output Files

**Check file existence:**

```bash
ls -lh data/discovery/
```

**Expected files:**

- [x]  `processo_links.json` (should be ~500KB - 2MB)
- [x]  `companies.json` (should be ~50-200KB)
- [x]  `discovery_summary.json` (should be ~5-20KB)

**Verify JSON structure:**

```bash
python -c "import json; print(json.load(open('data/discovery/processo_links.json'))['total_processos'])"
```

**Expected:**

- [x]  Number displayed (should be 400+) - No. I am using 2026, no more than 110 contracts, but it works.
- [x]  No JSON parsing errors

### 4. Verify Log Files

**Check log file:**

```bash
ls -lh logs/
```

**Expected:**

- [x]  `discovery_YYYYMMDD_HHMMSS.log` file exists
- [x]  File size >100KB (detailed logging)

**View log file:**

```bash
tail -100 logs/discovery_*.log
```

**Expected:**

- [x]  Clear log messages
- [x]  No ERROR level messages (warnings acceptable)
- [x]  Timestamps present

### 5. Data Quality Checks

**Check processo IDs:**

```bash
python -c "
import json
data = json.load(open('data/discovery/processo_links.json'))
for p in data['processos'][:10]:
    print(f\\"{p['processo_id']}: {p['company_name']}\\")
"
```

**Expected:**

- [ ]  Valid processo ID formats (e.g., TURCAP202500477)
- [ ]  Company names present
- [ ]  No empty or null values

**Check company totals:**

```bash
python -c "
import json
data = json.load(open('data/discovery/companies.json'))
for c in data['companies'][:10]:
    print(f\\"{c['company_name']}: {c['total_contracts']} contracts\\")
"
```

**Expected:**

- [ ]  Companies have >0 contracts
- [ ]  Numbers look reasonable

### 6. Run Integration Tests

```bash
python tests/integration/test_stage1_discovery.py
```

**Expected:**

- [ ]  All 5 tests pass
- [ ]  No assertion errors
- [ ]  Data consistency verified

## Performance Benchmarks

**Expected performance:**

- [ ]  Discovery completes in <30 minutes
- [ ]  Memory usage <500MB
- [ ]  CPU usage reasonable (spikes acceptable during scraping)

## Error Handling Tests

### Test 1: Invalid Year Filter

Edit `.env`: `FILTER_YEAR=9999`

```bash
python application/main.py
```

**Expected:**

- [ ]  Warning logged about filter
- [ ]  Process continues anyway
- [ ]  Completes successfully

### Test 2: Network Interruption

**Manually disconnect network mid-process**

**Expected:**

- [ ]  Error logged
- [ ]  Process stops gracefully
- [ ]  No crash/stack trace to console

### Test 3: Browser Close

**Manually close browser during scraping**

**Expected:**

- [ ]  Error detected
- [ ]  Process stops gracefully
- [ ]  Cleanup occurs

## Acceptance Criteria - Final Check

- [ ]  ✅ Successfully navigates ContasRio portal
- [ ]  ✅ Collects 400+ processo links
- [ ]  ✅ Zero PDFs downloaded during discovery
- [ ]  ✅ Completes in <30 minutes
- [ ]  ✅ All output files created with valid JSON
- [ ]  ✅ No critical errors in logs
- [ ]  ✅ Data quality looks good (spot checks)
- [ ]  ✅ Integration tests pass

# Stage 2 - MDAP
























