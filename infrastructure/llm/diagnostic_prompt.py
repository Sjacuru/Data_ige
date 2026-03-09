"""
infrastructure/llm/diagnostic_prompt.py

Prompt templates for the dual-path extraction diagnostic.

Two public functions — one per document type:

    build_contract_extraction_prompt(raw_text)
        → prompt for Groq to extract 5 fields from a contract raw text

    build_publication_extraction_prompt(raw_text)
        → prompt for Groq to extract 5 fields from a gazette publication raw text

These prompts are used by stage4_compliance.py to run LLM extraction in
parallel with the deterministic preprocessors.  The outputs are compared
field-by-field by extraction_comparator.py.

Design decisions
────────────────
- JSON-only output enforced in the prompt text AND via json_mode=True in
  GroqClient.call().  Double enforcement reduces hallucinated prose.
- null is used for missing fields — never empty string — so comparator
  can distinguish "field not found" from "field found but empty".
- Dates must be DD/MM/YYYY to match the deterministic preprocessor format.
- Raw text is truncated to MAX_RAW_CHARS (4000) before embedding.
  The first 4000 characters contain the header section of every contract
  and gazette extrato encountered in this project.
- Real examples from FIL-PRO-2023/00482 are embedded so the model has a
  concrete reference for Brazilian government contract format.
- No imports from domain/ or application/ — this is infrastructure only.
"""

# Maximum characters of raw text to embed in the prompt.
# First 4000 chars cover the header of every contract/publication seen.
MAX_RAW_CHARS = 4000

# ── Real example data (FIL-PRO-2023/00482) ────────────────────────────────────
# Used in prompt examples so the model has a concrete reference.
_CONTRACT_EXAMPLE_INPUT = (
    "EXTRATO DE CONTRATO Nº 002/2024 - PROCESSO Nº FIL-PRO-2023/00482 "
    "CONTRATANTE: DISTRIBUIDORA DE FILMES S/A - RIOFILME, CNPJ ... "
    "CONTRATADA: ARTE VITAL EXIBIÇÕES CINEMATOGRÁFICAS LTDA ... "
    "Data de assinatura: 16/09/2024"
)
_CONTRACT_EXAMPLE_OUTPUT = (
    '{\n'
    '  "processo_id":     "FIL-PRO-2023/00482",\n'
    '  "contract_number": "002/2024",\n'
    '  "signing_date":    "16/09/2024",\n'
    '  "contratante":     "DISTRIBUIDORA DE FILMES S/A - RIOFILME",\n'
    '  "contratada":      "ARTE VITAL EXIBIÇÕES CINEMATOGRÁFICAS LTDA"\n'
    '}'
)

_PUBLICATION_EXAMPLE_INPUT = (
    "D.O.RIO - DIÁRIO OFICIAL DO MUNICÍPIO DO RIO DE JANEIRO "
    "Segunda-feira, 30 de setembro de 2024 "
    "EXTRATO DE CONTRATO Nº 002/2024 - PROCESSO Nº FIL-PRO-2023/00482 "
    "CONTRATANTE: DISTRIBUIDORA DE FILMES S/A - RIOFILME "
    "CONTRATADA: ARTE VITAL EXIBIÇÕES CINEMATOGRÁFICAS LTDA"
)
_PUBLICATION_EXAMPLE_OUTPUT = (
    '{\n'
    '  "processo_id_in_pub":    "FIL-PRO-2023/00482",\n'
    '  "contract_number_in_pub":"002/2024",\n'
    '  "publication_date":      "30/09/2024",\n'
    '  "contratante_in_pub":    "DISTRIBUIDORA DE FILMES S/A - RIOFILME",\n'
    '  "contratada_in_pub":     "ARTE VITAL EXIBIÇÕES CINEMATOGRÁFICAS LTDA"\n'
    '}'
)


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def build_contract_extraction_prompt(raw_text: str) -> str:
    """
    Build the Groq prompt for extracting contract identity fields.

    Args:
        raw_text: Full raw text of the contract document.
                  Truncated to MAX_RAW_CHARS (4000) before embedding.

    Returns:
        A string prompt ready to send to GroqClient.call(..., json_mode=True).

    Expected LLM output (JSON object, 5 keys):
        {
          "processo_id":     string | null,   e.g. "FIL-PRO-2023/00482"
          "contract_number": string | null,   e.g. "002/2024"
          "signing_date":    string | null,   DD/MM/YYYY format only
          "contratante":     string | null,   full legal name of the hiring party
          "contratada":      string | null,   full legal name of the contracted party
        }
    """
    truncated = raw_text[:MAX_RAW_CHARS] if raw_text else ""

    return f"""You are a data extraction assistant for Brazilian public contract auditing.

TASK
────
Extract exactly 5 fields from the contract text below and return them as a
JSON object. Return ONLY the JSON object — no explanation, no markdown fences,
no preamble.

OUTPUT SCHEMA
─────────────
{{
  "processo_id":     <string or null>,
  "contract_number": <string or null>,
  "signing_date":    <string or null>,
  "contratante":     <string or null>,
  "contratada":      <string or null>
}}

FIELD DEFINITIONS
─────────────────
processo_id     : The processo number. Format examples: "FIL-PRO-2023/00482",
                  "TUR-PRO-2025/01221". Look for "PROCESSO Nº" or "Processo nº".
contract_number : The contract number. Format examples: "002/2024", "015/2025".
                  Look for "CONTRATO Nº" or "Contrato nº".
signing_date    : The date the contract was signed. Return as DD/MM/YYYY only.
                  Look for "Data de assinatura", "assinado em", "celebrado em".
contratante     : Full legal name of the hiring party (the government entity).
                  Look for "CONTRATANTE:" or "Contratante:".
contratada      : Full legal name of the contracted party (the company/supplier).
                  Look for "CONTRATADA:" or "Contratada:".

RULES
─────
- If a field cannot be found in the text, return null (not an empty string).
- Return dates in DD/MM/YYYY format only. If the date uses month names
  (e.g. "16 de setembro de 2024"), convert to "16/09/2024".
- Return full legal names as they appear in the text. Do not abbreviate.
- Return ONLY the JSON object. No prose. No markdown. No code fences.

EXAMPLE
───────
Input text:
{_CONTRACT_EXAMPLE_INPUT}

Expected output:
{_CONTRACT_EXAMPLE_OUTPUT}

CONTRACT TEXT TO EXTRACT FROM
──────────────────────────────
{truncated}"""


def build_publication_extraction_prompt(raw_text: str) -> str:
    """
    Build the Groq prompt for extracting publication identity fields.

    Args:
        raw_text: Full raw text of the gazette publication document.
                  Truncated to MAX_RAW_CHARS (4000) before embedding.

    Returns:
        A string prompt ready to send to GroqClient.call(..., json_mode=True).

    Expected LLM output (JSON object, 5 keys):
        {
          "processo_id_in_pub":    string | null,   gazette reference to processo
          "contract_number_in_pub":string | null,   gazette reference to contract
          "publication_date":      string | null,   DD/MM/YYYY format only
          "contratante_in_pub":    string | null,   hiring party name in gazette
          "contratada_in_pub":     string | null,   contracted party name in gazette
        }
    """
    truncated = raw_text[:MAX_RAW_CHARS] if raw_text else ""

    return f"""You are a data extraction assistant for Brazilian public contract auditing.

TASK
────
Extract exactly 5 fields from the official gazette (Diário Oficial) publication
text below and return them as a JSON object. Return ONLY the JSON object —
no explanation, no markdown fences, no preamble.

OUTPUT SCHEMA
─────────────
{{
  "processo_id_in_pub":    <string or null>,
  "contract_number_in_pub":<string or null>,
  "publication_date":      <string or null>,
  "contratante_in_pub":    <string or null>,
  "contratada_in_pub":     <string or null>
}}

FIELD DEFINITIONS
─────────────────
processo_id_in_pub     : The processo number referenced in the gazette entry.
                         Format examples: "FIL-PRO-2023/00482", "TUR-PRO-2025/01221".
                         Look for "PROCESSO Nº" or "Processo nº".
contract_number_in_pub : The contract number referenced in the gazette entry.
                         Format examples: "002/2024", "015/2025".
                         Look for "CONTRATO Nº" or "Contrato nº".
publication_date       : The date this gazette edition was published.
                         Return as DD/MM/YYYY only.
                         Look for the masthead date: "Segunda-feira, DD de mês de AAAA"
                         or "publicado em DD/MM/AAAA".
contratante_in_pub     : Full legal name of the hiring party as it appears in
                         the gazette. Look for "CONTRATANTE:".
contratada_in_pub      : Full legal name of the contracted party as it appears
                         in the gazette. Look for "CONTRATADA:".

RULES
─────
- If a field cannot be found in the text, return null (not an empty string).
- Return dates in DD/MM/YYYY format only. If the date uses month names
  (e.g. "30 de setembro de 2024"), convert to "30/09/2024".
- Return full legal names as they appear in the gazette text. Do not abbreviate.
- Return ONLY the JSON object. No prose. No markdown. No code fences.

EXAMPLE
───────
Input text:
{_PUBLICATION_EXAMPLE_INPUT}

Expected output:
{_PUBLICATION_EXAMPLE_OUTPUT}

GAZETTE TEXT TO EXTRACT FROM
─────────────────────────────
{truncated}"""