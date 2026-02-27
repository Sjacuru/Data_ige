# Epic 1 - **Discovery & Link Collection (ContasRio Portal)**

**Priority: CRITICAL** | **Estimated Time: 20-22 hours**

**Why:** We need to discover ALL available contracts before downloading anything. This prevents downloading 400+ PDFs at once and enables controlled one-at-a-time processing.

**What:** Navigate ContasRio portal, scrape all "favorecidos" (companies), discover navigation paths, collect processo links, and save metadata WITHOUT downloading any PDFs.

**Technical Breakdown:**

- **Portal Navigation**
    - Initialize Selenium WebDriver
    - Navigate to ContasRio contracts page
    - Apply year filter (configurable)
    - Wait for page load and verify navigation state
- **Company Discovery**
    - Scroll and collect all company rows from "favorecidos" list
    - Parse company data: Name, CNPJ, contract values
    - Handle pagination and dynamic content loading
    - Validate parsed data quality
- **Path Discovery Per Company**
    - For each company, click to navigate deeper
    - Discover all navigation paths (tree traversal)
    - Identify buttons/links at each level
    - Map complete navigation hierarchy
- **Processo Link Collection**
    - At deepest level, collect all processo links
    - Extract: processo ID, URL, associated company
    - Store link metadata (discovery path, timestamp)
    - Associate links with company/contract values
- **Output Generation**
    - Save to `data/discovery/processo_links.json`
    - Include: total count, company mapping, URLs
    - Save company metadata to `data/discovery/companies.json`
    - Generate discovery summary report

**Success Metrics:**

- Successfully navigate ContasRio portal 100% of time
- Collect all available processo links (400+ expected)
- Zero PDFs downloaded during this stage
- Complete discovery process in <30 minutes
- Valid JSON output with all required fields

**Deliverables:**

- `data/discovery/processo_links.json` (all discovered links)
- `data/discovery/companies.json` (company metadata)
- `logs/discovery_YYYYMMDD_HHMMSS.log` (audit trail)

**Data Output Example:**

json

`{
  "discovery_date": "2025-02-14T10:30:00",
  "total_companies": 45,
  "total_processos": 427,
  "processos": [
    {
      "processo_id": "TURCAP202500477",
      "url": "https://transparencia.rio/...",
      "company_name": "DANIELLA FONTENELLE GONÇALVES",
      "company_cnpj": "14.349.969/0001-87",
      "contract_value": "R$ 40.000,00",
      "discovery_path": ["RIOTUR", "Contratos", "2025"]
    }
  ]
}`