"""
Standalone test for text_preprocessor.py
=========================================
Run this to test preprocessing without executing the full pipeline.

Usage:
    python test_preprocessor.py
    
Or from project root:
    python Contract_analisys/test_preprocessor.py
"""

import sys
from pathlib import Path

# Add Contract_analisys to path if running from project root
sys.path.insert(0, str(Path(__file__).parent))

from Contract_analisys.text_preprocessor import preprocess_contract_text, print_summary


# ============================================================
# PASTE YOUR OCR TEXT HERE
# ============================================================

OCR_TEXT = """
"e. PREFEITURA DA CIDADE DO RIO DE JANEIRO VR Rio SECRETARIA MUNICIPAL
DE INFRAESTRUTURA E RERENTURA Fundação Instituto das Águas — Rio-AÁguas
RIO-ÁGUAS CONTRATO Nº 02/2025 Termo de Contrato celebrado entre a
FUNDAÇÃO INSTITUTO DAS ÁGUAS DO MUNICÍPIO DO RIO DE JANEIRO —
RIO-ÁGUAS, a seguir denominada, como CONTRATANTE, e a ENGESAN
ENGENHARIA E SANEAMENTO LTDA como CONTRATADA, para à execução dos
serviços, na forma abaixo. Aos dias ÁL do mês de março do ano de 2025,
na Rua Beatriz Larragoiti, nº 121 - Torre Norte - 4º andar - Ala Sul -
Complexo Rio Cidade Nova — Cidade Nova — Rio de Janeiro, a FUNDAÇÃO
INSTITUTO DAS ÁGUAS DO MUNICÍPIO DO RIO DE JANEIRO - RIO- ÁGUAS, a
seguir denominado CONTRATANTE, representado pelo presidente MARCELO DE
AGUIAR SEPÚLVIDA, matrícula nº13/177.057-7 e a sociedade ENGESAN
ENGENHARIA E SANEAMENTO LTDA, estabelecida na Avenida João Ribeiro, nº
373, Pilares — CEP: 20750-092 — Rio de Janeiro, inscrita no Cadastro
Nacional de Pessoas Jurídicas — CNPJ sob o nº 68.555.291/0001-18, a
seguir denominada CONTRATADA, neste ato representada por ANTONIO JOSE
OLSEN SARAIVA CÂMARA têm justo e acordado o presente Contrato, que é
celebrado em decorrência do resultado da CONCORRÊNCIA ELETRÔNICA CO -
RIO-ÁGUAS Nº 90233/2024, realizado por meio do processo administrativo
AGU-PRO-2024/00929, que se regerá pelas seguintes cláusulas e
condições. CLÁUSULA PRIMEIRA - LEGISLAÇÃO APLICÁVEL Este Contrato se
rege por toda a legislação aplicável à espécie, que desde já se entende
como referida no presente termo, especialmente pelas normas de caráter
geral da Lei Federal nº 14.133/2021, pela Lei Complementar Federal nº
123/2006 — Estatuto Nacional da Microempresa e da Empresa de Pequeno
Porte, pela Lei Complementar Federal nº 101/2000 — Lei de
Responsabilidade Fiscal, pelo Código de Defesa do Consumidor,
instituído pela Lei Federal nº 8.078/1990 e suas alterações, pelo
Código de Administração Financeira e Contabilidade Pública do Município
do Rio de Janeiro — CAF, instituído pela Lei nº 207/1980, e suas
alterações, ratificadas pela Lei Complementar nº 1/1990, pelo
Regulamento Geral do Código supra citado — RGCAF, aprovado pelo Decreto
Municipal nº 3.221/1981, e suas alterações, pela Lei Municipal nº
2.816/1999, pela Lei Municipal nº 4.352/06 e pelos Decretos Municipais
nº 17.907/99, 21.083/02, 21.253/02, 21.682/02, 27.078/06, 27.715/07,
31.349/09, 33.971/11, 46.195/2019, 49.415/2021 e 51.260/2022,
51.628/2022, 51.629/2022, 51.631/2022, 51.632/2022, 51.634/2022,
51.635/2022 e 51.689/2022,, com suas alterações posteriores, bem como
pelos preceitos de Direito Público, pelas regras constantes do Edital e
de seus Anexos, pela Proposta da CONTRATADA e pelas disposições deste
Contrato. A CONTRATADA declara conhecer todas essas normas e concorda
em se sujeitar às suas estipulações, sistema de penalidades e demais
regras delas constantes, ainda que não expressamente transcritas neste
instrumento, incondicional === e irrestritamente. === CLÁUSULA SEGUNDA
— OBJETO === O objeto do presente Contrato é a prestação dos serviços
de engenharia de "SERVIÇOS DE == OPERAÇÃO E MANUTENÇÃO DA ELEVATÓRIA E
DAS REDES DE DRENAGEM DA === 2 COMUNIDADE SÃO FERNANDO — SANTA CRUZ
—XIX R.A.— A.P. 5.3", sob regime de ==". empreitada por Preço Unitário,
conforme as especificações constantes do Projeto Básico aprovado, Termo
=== de Referência, Elementos Complementares e Parcela de Relevância de
fls. 441-461/464-469 do sã Â . ==. administrativo nº AGU-PRO-2024/000929.

Autenticado com senha por GABRIELLE ESPIRITO SANTO BARBOSA GOMES - ESTAGIARIO TECNICO EM ADMINISTRACAO / 51793 - 14/03/2025 às 10:06:35.
Documento Nº: 9552697-8834 - consulta à autenticidade em https://acesso.processo.rio/sigaex/public/app/autenticar?n=9552697-8834
SIGA À
"""


# ============================================================
# RUN TEST
# ============================================================

def main():
    print("\n" + "=" * 60)
    print("🧪 TEXT PREPROCESSOR TEST")
    print("=" * 60)
    
    # Show original
    print(f"\n📥 INPUT TEXT:")
    print(f"   Length: {len(OCR_TEXT):,} characters")
    print(f"   Preview: {OCR_TEXT[:100].strip()}...")
    
    # Run preprocessing
    print("\n⚙️  Processing...")
    result = preprocess_contract_text(OCR_TEXT)
    
    # Show summary
    print_summary(result)
    
    # Show sections found
    if result.sections_found:
        print("\n📑 SECTIONS DETECTED:")
        for i, section in enumerate(result.sections_found, 1):
            print(f"   {i}. [{section['type']}] {section['title']}")
    
    # Show metadata removed
    if result.metadata_removed:
        print("\n🗑️  METADATA REMOVED:")
        for item in result.metadata_removed[:5]:
            print(f"   • {item[:60]}...")
    
    # Show cleaned text
    print("\n" + "=" * 60)
    print("📄 CLEANED TEXT (first 3500 chars):")
    print("=" * 60)
    print(result.structured_text[:3500])
    
    if len(result.structured_text) > 3500:
        print(f"\n... [{len(result.structured_text) - 3500:,} more characters]")
    
    # Compare before/after
    print("\n" + "=" * 60)
    print("📊 COMPARISON:")
    print("=" * 60)
    print(f"   Before: {result.original_length:,} chars")
    print(f"   After:  {result.final_length:,} chars")
    print(f"   Removed: {result.original_length - result.final_length:,} chars ({result.reduction_percent:.1f}%)")
    
    return result


if __name__ == "__main__":
    result = main()
    
    # Optional: Save to file for inspection
    save = input("\n💾 Save cleaned text to file? (y/n): ").strip().lower()
    if save == 'y':
        output_path = Path("test_preprocessed_output.txt")
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("=== ORIGINAL ===\n\n")
            f.write(OCR_TEXT)
            f.write("\n\n=== CLEANED ===\n\n")
            f.write(result.structured_text)
        print(f"✅ Saved to: {output_path}")