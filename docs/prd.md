**Contract Analisys— PRD v0**

**Mission**

As a public contract auditor, I want to reduce manual chacks, increase coverage and detect inconsistencies earlier and sistematicaly from the institution by making simple reasoning tasks evaluated by AI-based tools. The current auditing process scenario is misaligned with recent technological achievements, and over time companies will sell tools that will not be customized and will raise costs for local citizens in the short run.

**Problem**

The contracts and tasks performed by auditors have a large number of repetitive components that are remarkably simple and require checks that can be easily reasoned. The structure of auditing tasks does not allow the separation of simple tasks that can be completely isolated and that do not interfere with more complex tasks. The auditor needs to walk through both simple and complex tasks himself, because leaving the simple ones to a less important role would include one more step in an already overloaded process engine. It has a higher cost, reductions of the effectivity and less coverage for more relevant subjects.

**Solution**

A software solution that can analyze predefined simpler items of a checklist, enhancing productivity, optimizing processes, augmenting analysis, and scaling it by being checked in a more extensive and accurate manner. By retrieving data from contracts, laws, public and private websites, and other sources related to the auditing documents in order to check complince regulations, it is possible to apply a modeling process that uses a dynamic sequence of code evaluation, which concatenates and reuses both deterministic and probabilistic approaches in the reasoning activity. With that, it will be possible to obtain a comprehensive and reliable output. This is a primarily internal tool and will expand for others institutions that perform the same work for free. It will deliver a suggestion for a final decision or judgement and help decide over future activities strategicaly and operational. 

Core Compliance Rules:

1. Publication must occur within 20 days of contract signing
2. Publication must reference correct contract identifiers
3. Publication must include all mandatory parties

**Target Users**

Auditors and technicians from account courts from Rio de Janeiro city or even any city or state that promote contract analysis using the same or seamless rules to perform evaluations.

Primary Users:

- Contract Auditors and technicians: Review contracts and conduct audits (in loco or remotely), generating demands for companies.
Primary need: Speed to increase coverage and quality.

Secondary Users:

- Court Directors: Require summary reports for oversight and strategic decision-making.

**Features (Priority Order)**

1. Data Retrieval

1.1 Contract Data  Extraction

Why: Enables the auditor to check whether the contractual terms, responsibilities, and execution conditions are clearly extracted and available for compliance verification.

**What**:

- The system extracts structured data from a contract document and stores it in a predefined JSON schema.
- Information related to the contract execution
- Document that bind actors and sets responsabilities
    
    **Extraction**
    
    - Source:
        - Contract documents retrieved from public websites
    - Extracted elements:
        - Contract execution information
        - Parties involved
        - Roles and responsibilities
        - Contract object
        - System automatically discovers all navigation paths within company pages
        - Handles both PDF downloads and web page extraction
        - Associates each contract with unique processo identifiers
    
    **Reasoning**
    
    - Use LLM-based document parsing to:
        - Identify relevant sections
        - Map textual content to predefined JSON fields
    - Validate that all required fields are present or explicitly marked as missing
    
    **Output**
    
    - A JSON file containing:
        - Structured contract data
        - Metadata (source, extraction timestamp)
        - Flags for missing or ambiguous fields

**Verification method**: Use LLM analysis to recover the necessary data from the contract and save it in a predefined JSON format.

**Data source**: Multiple websites provide the data throught scrapping

1.2 Publishing Data  Extraction

Why: Allows the auditor to check whether the contract was published correctly and within the legally required timeframe.

**What**: The system extracts publication-related data and confirms linkage between the publication and the corresponding contract.

**Extraction**

- Source:
    - Official publication webpages
- Extracted elements:
    - Publication date
    - Contract reference identifiers
    - Names of parties involved
    - Search official gazette (DoWeb) using processo number
    - Handle CAPTCHA challenges automatically (with manual fallback when needed)
    - Download publication PDFs when available

**Reasoning**

- Use LLM-based parsing to:
    - Match publication data to contract identifiers
    - Normalize dates and entity names
- Flag inconsistencies between contract and publication data

**Output**

- A JSON file containing:
    - Structured publication data
    - Normalized identifiers
    - Consistency flags (match / mismatch)

Verification method: Use LLM analysis to recover the necessary data from the publication and save it in JSON format.

**Data source**: Publication webpage

**2. AI Validation of Retrieved Data**

**Why**:  Supports the auditor’s evaluation on whether the contract complies with publication and formal disclosure rules.

**What**: The system produces a rule-based compliance assessment derived from structured contract and publication data.

**Extraction**

- Input:
    - Contract JSON (from Feature 1.1)
    - Publication JSON (from Feature 1.2)

**Reasoning**

- Apply a reasoning pipeline that:
    - Evaluates predefined compliance rules
    - Uses deterministic checks (e.g., date comparisons)
    - Uses probabilistic reasoning where ambiguity exists
- Each rule evaluation produces:
    - Pass / Fail / Uncertain
    - Explanation trace

**Output**

- A compliance JSON containing:
    - Rule-by-rule evaluation results
    - Overall compliance status
    - Confidence indicators
    - Human-readable explanation

**Verification method**: Retrieve initial extractions from the contract and publication, provide them to the LLM for analysis in JSON format, and generate a final analysis based on it.

**Data**: JSON data retrieved in previous paths.

**UI Behavior**

**3. Dashboard** 

**Why**: Allows the auditor to decide when to trust, retry, or intervene in automated extraction and analysis steps.

**What**: A dashboard that exposes system state, execution controls, and analysis results in a structured and auditable manner.

**Extraction**

- Inputs:
    - Stored contract files
    - Publication data
    - JSON outputs from extraction and reasoning steps

**Reasoning**

- Aggregate system state to:
    - Detect incomplete pipelines
    - Identify extraction or reasoning failures
- No autonomous decision-making; only aggregation and signaling

**Output**

- UI elements that display:
    - Process status per contract (analyzed, pending, failed)
    - Actionable buttons:
        - Trigger scraping
        - Trigger download
        - Trigger publication scraping
        - Trigger analysis
    - Toggle to execute full pipeline end-to-end

**Data**: Stored contracts, publications, JSON-formatted information.

**4. Report**

**Why**: Enables the auditor and supervisors to decide whether contracts and responsible parties are complying with applicable rules and whether further investigation is required.

**What**: A generated report summarizing extraction coverage, analysis status, and detected irregularities.

**Extraction**

- Inputs:
    - Compliance JSON outputs
    - Contract metadata

**Reasoning**

- Aggregate results to:
    - Count analyzed vs non-analyzed contracts
    - Highlight missing analyses
    - Group detected irregularities by type or severity

**Output**

- A report view containing:
    - Total contracts extracted
    - Total contracts analyzed
    - Detailed list of non-analyzed contracts, including:
        - Organization name
        - Company name
        - Contract value
        - Contract object summary
        - Irregularities detected

**Data**: JSON format retrieved from contracts in previous steps

**Asset Mapping**

Data Assets:

- Contract PDFs (stored the file or use OCR and other techiniques to get the text and prevent use of HD space. There will be more procesing required and 400 is the amount of contracts)
- Extraction JSONs (instead of PDF files)
- Publication PDFs (same as contracts)
- Analysis results (JSON)

Code Assets:

- domain/ - Business logic
- infrastructure/ - Technical implementations
- application/ - Orchestration

External Dependencies:

- Groq API (LLM extraction)
- Selenium (Web scraping)
- ContasRio portal and Transparência portal(contract source)
- DoWeb portal (publication source)

**Scope** 

**Phase 1** 

This system validates the technical feasibility of AI-assisted contract auditing by implementing a subset of compliance rules:

1. Publication Timeliness (Rule R001)
   - Contract published within 20 days
   - Deterministic check
   
2. Party Name Matching (Rule R002)
   - Contract parties match publication parties
   - Probabilistic LLM-based check

**Future Phases**

Additional compliance rules will be added incrementally after validation. The system architecture needs support extensibility through a pluggable rule engine.

**Security**

The system will have no interaction for chat at first place, but LLM interaction can alucinate some data and compromise the analisys. The output must be reviewed by the responsible auditor during implementation phase.

AI will suggest accountability and send it for a human verification.

Logs must be generated afetr each test and before activitie sign-off 

Others:

- API key management
- Data privacy considerations
- Access control
- Include explanation on how to handle customization for interested parts outside of Rio.

**Potential Users Positioning**

The tool should be configurable to serve the greatest number of interested institutions. Each city or state has its own set of laws, and they differ in many aspects, which makes it necessary to allow some level of adaptation.

The auditors can resist in colaborate for the tool`s enhancement fearing be replaced and directed to a meaningless role. 

An explanation about the AI capabilities and show that it will alow the auditor to concentrate effort on what matter most on every day activities can mitigate and improve productivity.