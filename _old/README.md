# Contract Analysis System

> AI-powered contract auditing tool for public procurement compliance

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

## 📋 Overview

The **Contract Analysis System** automates the extraction and compliance verification of public contracts, reducing manual audit time by up to 60% while increasing coverage and accuracy. This tool is designed for auditors at municipal and state account courts who need to verify contract publication compliance systematically.

### The Problem

Public contract auditors spend much of their time on simple, repetitive compliance checks:
- Was the contract published on time?
- Do the published details match the contract?
- Are all required parties listed?

This leaves less time for complex analysis that truly requires human expertise.

### The Solution

An AI-assisted system that:
- ✅ **Extracts** contract data from government portals automatically
- ✅ **Retrieves** official publications from digital gazettes  
- ✅ **Validates** compliance with configurable rules
- ✅ **Reports** findings in auditor-friendly formats
- ✅ **Scales** to hundreds of contracts per batch

**Key Innovation:** Hybrid approach combining deterministic rules (dates, identifiers) with AI-powered semantic matching (party names, contract descriptions).

### Prerequisites

- Python 3.9 or higher
- Google Chrome browser (for web scraping)
- Groq API key (for AI extraction) - [Get one free](https://console.groq.com)

## 📂 Project Structure

```
contract-analysis/
├── domain/                     # Business logic (no external dependencies)
│   ├── models/                # Data entities (Contract, Publication)
│   └── services/              # Business rules (ConformityChecker)
│
├── infrastructure/            # Technical implementations
│   ├── scrapers/             
│   │   ├── contasrio/        # Contract portal scraper
│   │   └── doweb/            # Publication gazette scraper
│   ├── extractors/           # AI-powered data extraction
│   ├── web/                  # Selenium utilities (driver, CAPTCHA)
│   └── persistence/          # Data storage (JSON, Excel)
│
├── application/              # Workflows and entry points
│   ├── workflows/            # Business process orchestration
│   ├── main.py              # CLI entry point
│   └── app.py               # Streamlit UI (optional)
│
├── data/                     # Data storage
│   ├── downloads/           # Downloaded PDFs
│   ├── extractions/         # Extracted JSON data
│   └── outputs/             # Generated reports
│
├── tests_new/               # Test suite
│   ├── unit/               # Fast tests (no Selenium)
│   └── integration/        # Slow tests (with browser)
│
├── config.py               # Configuration
├── requirements.txt        # Python dependencies
└── README.md              # This file
```

### Architecture Principles

This project follows **Domain-Driven Design (DDD)** and **Clean Architecture**:

- **Domain Layer:** Pure business logic with no technical dependencies
- **Infrastructure Layer:** Technical implementations (web scraping, AI, storage)
- **Application Layer:** Workflows that orchestrate domain + infrastructure

**Why this matters:** You can test business rules without starting a browser, swap AI providers easily, and add new data sources without changing core logic.

```
┌─────────────────────────────────────────────────────────────┐
│ 1. SCRAPE CONTRACTS (ContasRio Portal)                     │
│    ├─ Navigate to contracts page                           │
│    ├─ Discover all navigation paths                        │
│    ├─ Collect processo links                               │
│    └─ Download PDFs or extract web content                 │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. EXTRACT CONTRACT DATA (AI-Powered)                      │
│    ├─ Extract data from text in PDFs                               │
│    ├─ Send to LLM (Groq) with structured prompt            │
│    ├─ Parse JSON response                                  │
│    └─ Save structured data                                 │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. SEARCH PUBLICATIONS (DoWeb Portal)                      │
│    ├─ Search by processo number                            │
│    ├─ Handle CAPTCHA (hybrid approach)                     │
│    ├─ Download publication PDF                             │
│    └─ Extract publication data                             │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. VALIDATE COMPLIANCE (Rule Engine)                       │
│    ├─ Check publication timeliness (≤20 days)              │
│    ├─ Match party names (AI-assisted)                      │
│    ├─ Verify contract identifiers                          │
│    └─ Generate conformity result                           │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. GENERATE REPORT (Excel)                                 │
│    ├─ Aggregate results                                    │
│    ├─ Format findings                                      │
│    ├─ Add metadata                                         │
│    └─ Export to data/outputs/                              │
└─────────────────────────────────────────────────────────────┘
```

### Key Technologies

- **Web Scraping:** Selenium (Chrome WebDriver)
- **AI Extraction:** Groq API (Llama 3.3 70B)
- **PDF Processing:** PyMuPDF, Tesseract OCR
- **Data Storage:** JSON, Excel (openpyxl)
- **CAPTCHA Handling:** Hybrid manual/automated approach

---

## 🗺️ Roadmap

### Phase 0: Proof of Concept ✅ (Current)
- [ ] Contract extraction from ContasRio
- [ ] Publication extraction from DoWeb
- [ ] Basic compliance validation
- [ ] Excel report generation

### Phase 1: Technical Validation (Q2 2025)
- [ ] 90%+ extraction accuracy
- [ ] 85%+ publication search success rate
- [ ] Automated testing suite

### Phase 2: User Validation (Q3 2025)
- [ ] savings demonstrated
- [ ] Feedback-driven improvements

### Phase 3: Business Validation (Q4 2025)
- [ ] Zero false negatives on critical rules
- [ ] Management approval for Phase 4

### Phase 4: Epic Implementation (2026)
- [ ] Advanced compliance rules 
- [ ] Interactive dashboard
- [ ] Quality check workflows
- [ ] Configurable rule engine

### Phase 5: MDAP Integration (2026)
- [ ] AI supervisor bot
- [ ] Intelligent case routing
- [ ] Learning from auditor decisions

### Phase 6: Production Deployment (2026+)
- [ ] Monitoring & alerting
- [ ] Continuous improvement loops
- [ ] Multi-city deployment
- [ ] Open-source community edition

---

### Data Handling

- ✅ Contract data processed locally (not sent to third parties except LLM)
- ✅ API keys stored in environment variables
- ✅ Audit logs maintained for all operations
- ✅ Human review required for all compliance decisions

### Known Limitations

⚠️ **LLM Hallucination Risk:** AI-extracted data may contain errors. Always verify critical information.

⚠️ **CAPTCHA Dependency:** DoWeb may require manual CAPTCHA solving in some cases.

⚠️ **Portal Changes:** System may break if source portals change structure.


---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

### Third-Party Licenses

- Selenium: Apache 2.0
- PyMuPDF: AGPL-3.0
- Groq SDK: Apache 2.0

---

## 🙏 Acknowledgments

- Rio de Janeiro Municipal Account Court for domain expertise
- Groq for providing LLM API access
- Open-source community for foundational tools

---

- **Project contact:** (mailto:sjacuru@gmail.com.br)
- **Institution:** Rio de Janeiro Municipal Account Court / Tribunal de Contas do Município do Rio de Janeiro

---

## 📈 Project Stats

- **Languages:** Python 100%
- **Lines of Code:** ~5,000
- **Test Coverage:** TBD
- **Contributors:** See [CONTRIBUTORS.md](CONTRIBUTORS.md)

---

## ⚖️ Legal Notice

This tool is provided for legitimate public auditing purposes only. Users are responsible for:
- Compliance with applicable laws and regulations
- Proper handling of sensitive government data
- Verification of AI-generated outputs
- Adherence to institutional policies

**This is not legal advice.** The tool assists auditors but does not replace professional judgment.

---

<div align="center">

</div>
