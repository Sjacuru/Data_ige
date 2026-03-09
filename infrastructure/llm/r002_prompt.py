"""
infrastructure/llm/r002_prompt.py

Prompt template for Rule R002 — Party Name Semantic Comparison.

One public function:

    build_r002_prompt(contract_contratante, pub_contratante,
                      contract_contratada, pub_contratada)
        → prompt string for GroqClient.call(..., json_mode=True)

Why LLM for R002
────────────────
Brazilian public contract documents and gazette publications frequently
use different representations of the same legal entity:

    Contract  : "DISTRIBUIDORA DE FILMES S/A - RIOFILME"
    Gazette   : "Distribuidora de Filmes S.A - RIOFILME"

    Contract  : "ARTE VITAL EXIBIÇÕES CINEMATOGRÁFICAS LTDA"
    Gazette   : "Arte Vital Exibições Cinematográficas LTDA ME"

Simple string normalisation handles case and punctuation but cannot
determine whether "LTDA ME" is the same entity as "LTDA" — that requires
semantic reasoning about Brazilian company suffix conventions.

The LLM is given both representations and asked to decide whether each
pair refers to the same legal entity, with an explanation for each decision.

Output schema
─────────────
{
  "contratante_match":       bool,
  "contratada_match":        bool,
  "contratante_explanation": string,
  "contratada_explanation":  string,
  "overall_verdict":         "PASS" | "FAIL",
  "confidence":              "high" | "medium" | "low"
}

Verdict rules (enforced in the prompt):
  overall_verdict = "PASS"  iff  contratante_match AND contratada_match
  overall_verdict = "FAIL"  if   either is False
  confidence = "low"        if   either party string is null/empty,
                                 or if names are substantially different
                                 with no clear abbreviation relationship

compliance_engine.evaluate_r002() treats confidence="low" as INCONCLUSIVE
regardless of the verdict — this is intentional.
"""

# ── Real example (FIL-PRO-2023/00482) ─────────────────────────────────────────
_EXAMPLE_INPUT = {
    "contract_contratante": "DISTRIBUIDORA DE FILMES S/A - RIOFILME",
    "pub_contratante":      "Distribuidora de Filmes S.A - RIOFILME",
    "contract_contratada":  "ARTE VITAL EXIBIÇÕES CINEMATOGRÁFICAS LTDA",
    "pub_contratada":       "Arte Vital Exibições Cinematográficas LTDA",
}

_EXAMPLE_OUTPUT = """{
  "contratante_match":       true,
  "contratada_match":        true,
  "contratante_explanation": "Both refer to the same entity. 'S/A' and 'S.A' are equivalent Brazilian company suffixes (Sociedade Anônima). 'RIOFILME' appears in both.",
  "contratada_explanation":  "Names are identical except for case difference. Same legal entity.",
  "overall_verdict":         "PASS",
  "confidence":              "high"
}"""


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC FUNCTION
# ══════════════════════════════════════════════════════════════════════════════

def build_r002_prompt(
    contract_contratante: str | None,
    pub_contratante:      str | None,
    contract_contratada:  str | None,
    pub_contratada:       str | None,
) -> str:
    """
    Build the Groq prompt for R002 party name semantic comparison.

    Args:
        contract_contratante : Hiring party name from the contract document.
        pub_contratante      : Hiring party name from the gazette publication.
        contract_contratada  : Contracted party name from the contract document.
        pub_contratada       : Contracted party name from the gazette publication.

    Returns:
        A prompt string ready to send to GroqClient.call(..., json_mode=True).

    Note:
        None values are rendered as the string "null" in the prompt.
        The LLM is instructed to return confidence="low" when any field is null.
    """
    def _render(v): return v if v else "null"

    ct_c = _render(contract_contratante)
    ct_p = _render(pub_contratante)
    ca_c = _render(contract_contratada)
    ca_p = _render(pub_contratada)

    return f"""You are a compliance assistant for Brazilian public contract auditing.

TASK
────
Determine whether the party names in a contract document match the party names
in the corresponding official gazette (Diário Oficial) publication.

Party names in Brazilian government contracts often differ between documents
due to: abbreviations, legal suffix variations (S/A vs S.A, LTDA vs LTDA ME),
case differences, or minor formatting differences. Your job is to determine
whether each pair refers to the same legal entity.

PARTY NAMES TO COMPARE
───────────────────────
CONTRATANTE (hiring party — typically the government entity):
  Contract  : {ct_c}
  Gazette   : {ct_p}

CONTRATADA (contracted party — typically the company or supplier):
  Contract  : {ca_c}
  Gazette   : {ca_p}

OUTPUT SCHEMA
─────────────
Return ONLY a JSON object with exactly these 6 keys. No prose. No markdown.

{{
  "contratante_match":       <true or false>,
  "contratada_match":        <true or false>,
  "contratante_explanation": <string — one sentence explaining your decision>,
  "contratada_explanation":  <string — one sentence explaining your decision>,
  "overall_verdict":         <"PASS" or "FAIL">,
  "confidence":              <"high", "medium", or "low">
}}

VERDICT RULES
─────────────
overall_verdict must be "PASS" only if BOTH contratante_match AND contratada_match are true.
overall_verdict must be "FAIL" if either match is false.

CONFIDENCE RULES
────────────────
Use "high"   when the names clearly refer to the same entity (minor formatting only).
Use "medium" when there is some uncertainty but a reasonable match can be determined.
Use "low"    when:
  - Either party name is null or empty
  - Names are substantially different with no clear abbreviation relationship
  - You cannot determine with confidence whether they refer to the same entity

IMPORTANT: When confidence is "low", the human auditor will review this contract
manually. It is better to flag uncertainty than to give a wrong confident answer.

COMMON BRAZILIAN EQUIVALENCES
──────────────────────────────
- S/A = S.A = S.A. (Sociedade Anônima)
- LTDA = Ltda = Ltda. (Limitada)
- LTDA ME = LTDA (ME = Microempresa suffix, same entity)
- EPP = Empresa de Pequeno Porte (suffix variation)
- Case differences: "EMPRESA" = "Empresa" = "empresa"
- Punctuation: "S/A" = "S.A" = "S A" (slash, dot, space variants)
- Government entities often appear with/without full acronym expansion

EXAMPLE
───────
Contract contratante : {_EXAMPLE_INPUT['contract_contratante']}
Gazette  contratante : {_EXAMPLE_INPUT['pub_contratante']}
Contract contratada  : {_EXAMPLE_INPUT['contract_contratada']}
Gazette  contratada  : {_EXAMPLE_INPUT['pub_contratada']}

Expected output:
{_EXAMPLE_OUTPUT}

Return ONLY the JSON object. No explanation outside the JSON.
"""