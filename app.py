import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import datetime

from Contract_analisys.contract_extractor import (
    process_all_contracts,
    process_single_contract,
    export_to_excel,
    export_to_json,
    get_folder_stats,
    load_analysis_summary,
    extract_text_from_pdf
)

from config import (
    PROCESSOS_DIR,
    ANALYSIS_SUMMARY_CSV,
    EXTRACTIONS_DIR
)

PDF_FOLDER = PROCESSOS_DIR
CSV_PATH = ANALYSIS_SUMMARY_CSV
OUTPUT_FOLDER = EXTRACTIONS_DIR

st.set_page_config(
    page_title="Contract Analyzer - Processo.rio",
    page_icon="📄",
    layout="wide"
)

st.title("📄 Contract Analyzer")
st.markdown("Extract and analyze contract data from processo.rio PDFs")

if "extraction_results" not in st.session_state:
    st.session_state.extraction_results = []
if "processing" not in st.session_state:
    st.session_state.processing = False


st.sidebar.markdown("### Debug paths")
st.sidebar.code(f"""
PDF_FOLDER = {PDF_FOLDER}
CSV_PATH = {CSV_PATH }
OUTPUT_FOLDER = {OUTPUT_FOLDER}
""")

tab1, tab2, tab3, tab4 = st.tabs(["📊 Dashboard", "🔄 Extract Data", "📋 Results", "📥 Export"])

with tab1:
    st.header("Overview")
    
    col1, col2, col3 = st.columns(3)
    
    folder_stats = get_folder_stats(PDF_FOLDER)
    
    with col1:
        st.metric("PDF Files Available", folder_stats.get("total_files", 0))
    
    with col2:
        st.metric("Total Size", f"{folder_stats.get('total_size_mb', 0)} MB")
    
    with col3:
        extracted_count = len(st.session_state.extraction_results)
        st.metric("Contracts Extracted", extracted_count)
    
    st.divider()
    
    st.subheader("Analysis Summary (CSV)")
    summary_df = load_analysis_summary(CSV_PATH)
    
    if not summary_df.empty:
        st.dataframe(summary_df, width="stretch")
    else:
        st.info(f"No analysis summary found at `{CSV_PATH}`. Upload your CSV or ensure the file exists.")
        
        uploaded_csv = st.file_uploader("Upload analysis_summary.csv", type=["csv"])
        if uploaded_csv:
            Path(CSV_PATH).parent.mkdir(parents=True, exist_ok=True)
            df = pd.read_csv(uploaded_csv)
            df.to_csv(CSV_PATH, index=False)
            st.success("CSV uploaded successfully!")
            st.rerun()
    
    if folder_stats.get("total_files", 0) > 0:
        st.subheader("Available PDF Files")
        with st.expander("View PDF files", expanded=False):
            for f in folder_stats.get("files", []):
                st.text(f"📄 {f}")

with tab2:
    st.header("Extract Contract Data")
    
    st.markdown("""
    This will:
    1. Read all PDFs from the downloads folder
    2. Extract text using PyMuPDF
    3. Use AI to identify key contract information
    4. Link data with Processo IDs from the CSV
    """)
    
    folder_stats = get_folder_stats(PDF_FOLDER)
    
    if not folder_stats.get("exists"):
        st.warning(f"Folder `{PDF_FOLDER}` does not exist. Please ensure your PDFs are in this location.")
        
        if st.button("Create Folder Structure"):
            Path(PDF_FOLDER).mkdir(parents=True, exist_ok=True)
            Path(OUTPUT_FOLDER).mkdir(parents=True, exist_ok=True)
            st.success("Folders created!")
            st.rerun()
    
    elif folder_stats.get("total_files", 0) == 0:
        st.warning("No PDF files found in the folder. Please add your contract PDFs.")
        
        uploaded_pdfs = st.file_uploader(
            "Upload PDF files", 
            type=["pdf"], 
            accept_multiple_files=True
        )
        
        if uploaded_pdfs:
            for pdf in uploaded_pdfs:
                save_path = PDF_FOLDER / pdf.name
                with open(save_path, "wb") as f:
                    f.write(pdf.getbuffer())
            st.success(f"Uploaded {len(uploaded_pdfs)} PDF files!")
            st.rerun()
    
    else:
        st.success(f"Found {folder_stats['total_files']} PDF files ready for extraction")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🚀 Start Extraction", type="primary", disabled=st.session_state.processing):
                st.session_state.processing = True
                
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                def update_progress(current, total, file_name):
                    progress_bar.progress(current / total)
                    status_text.text(f"Processing: {file_name} ({current}/{total})")
                
                with st.spinner("Extracting contract data..."):
                    results = process_all_contracts(
                        pdf_folder=str(PDF_FOLDER),
                        csv_path=str(CSV_PATH),
                        progress_callback=update_progress
                    )
                
                st.session_state.extraction_results = results
                st.session_state.processing = False
                
                success_count = sum(1 for r in results if r.get("success"))
                st.success(f"Extraction complete! {success_count}/{len(results)} successful")
                
                progress_bar.empty()
                status_text.empty()
        
        with col2:
            if st.button("🔄 Clear Results"):
                st.session_state.extraction_results = []
                st.rerun()
        
        st.divider()
        st.subheader("Extract Single File")
        
        pdf_files = folder_stats.get("files", [])
        selected_file = st.selectbox("Select a PDF to extract", [""] + pdf_files)
        
        if selected_file and st.button("Extract Selected"):
            pdf_path = str(Path(PDF_FOLDER) / selected_file)
            
            with st.spinner(f"Extracting {selected_file}..."):
                result = process_single_contract(pdf_path)
            
            if result.get("success"):
                st.success("Extraction successful!")
                
                with st.expander("View Extracted Data", expanded=True):
                    data = result.get("extracted_data", {})
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("**Contract Value:**")
                        st.write(data.get("valor_contrato", "Not found"))
                        
                        st.markdown("**Validity Period:**")
                        st.write(f"{data.get('data_inicio', 'N/A')} to {data.get('data_fim', 'N/A')}")
                        
                        st.markdown("**Contractor:**")
                        st.write(data.get("contratante", "Not found"))
                    
                    with col2:
                        st.markdown("**Contract Type:**")
                        st.write(data.get("tipo_contrato", "Not found"))
                        
                        st.markdown("**Contracted Party:**")
                        st.write(data.get("contratada", "Not found"))
                        
                        st.markdown("**Object/Purpose:**")
                        st.write(data.get("objeto", "Not found"))
                    
                    st.markdown("**Main Clauses:**")
                    clauses = data.get("clausulas_principais", [])
                    if clauses:
                        for clause in clauses:
                            st.markdown(f"- {clause}")
                    else:
                        st.write("No clauses extracted")
            else:
                st.error(f"Extraction failed: {result.get('error')}")

with tab3:
    st.header("Extraction Results")
    
    if not st.session_state.extraction_results:
        st.info("No extraction results yet. Go to 'Extract Data' tab to process contracts.")
    else:
        results = st.session_state.extraction_results
        
        success_count = sum(1 for r in results if r.get("success"))
        error_count = len(results) - success_count
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Processed", len(results))
        with col2:
            st.metric("Successful", success_count)
        with col3:
            st.metric("Errors", error_count)
        
        st.divider()
        
        filter_status = st.selectbox(
            "Filter by status",
            ["All", "Successful", "Errors"]
        )
        
        filtered = results
        if filter_status == "Successful":
            filtered = [r for r in results if r.get("success")]
        elif filter_status == "Errors":
            filtered = [r for r in results if not r.get("success")]
        
        for i, result in enumerate(filtered):
            with st.expander(f"📄 {result.get('file_name', 'Unknown')} - {'✅' if result.get('success') else '❌'}", expanded=False):
                if result.get("success"):
                    data = result.get("extracted_data", {})
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.markdown("**Basic Information**")
                        st.write(f"- **Processo ID:** {result.get('processo_id', 'N/A')}")
                        st.write(f"- **Total Pages:** {result.get('total_pages', 0)}")
                        st.write(f"- **Paragraphs:** {result.get('paragraph_count', 0)}")
                        st.write(f"- **Contract Number:** {data.get('numero_contrato', 'N/A')}")
                        st.write(f"- **Contract Type:** {data.get('tipo_contrato', 'N/A')}")
                    
                    with col2:
                        st.markdown("**Financial & Dates**")
                        st.write(f"- **Value:** {data.get('valor_contrato', 'N/A')} {data.get('moeda', '')}")
                        st.write(f"- **Start Date:** {data.get('data_inicio', 'N/A')}")
                        st.write(f"- **End Date:** {data.get('data_fim', 'N/A')}")
                        st.write(f"- **Duration:** {data.get('vigencia_meses', 'N/A')} months")
                    
                    st.markdown("**Parties**")
                    st.write(f"- **Contractor:** {data.get('contratante', 'N/A')} (CNPJ: {data.get('contratante_cnpj', 'N/A')})")
                    st.write(f"- **Contracted:** {data.get('contratada', 'N/A')} (CNPJ: {data.get('contratada_cnpj', 'N/A')})")
                    
                    st.markdown("**Object/Purpose**")
                    st.write(data.get("objeto", "Not found"))
                    
                    clauses = data.get("clausulas_principais", [])
                    if clauses:
                        st.markdown("**Main Clauses**")
                        for clause in clauses:
                            st.markdown(f"- {clause}")
                    
                    if st.checkbox(f"Show paragraphs ({result.get('paragraph_count', 0)})", key=f"para_{i}"):
                        for j, para in enumerate(result.get("paragraphs", [])[:20]):
                            st.text_area(f"Paragraph {j+1}", para, height=100, key=f"para_{i}_{j}")
                        if result.get("paragraph_count", 0) > 20:
                            st.info(f"Showing first 20 of {result.get('paragraph_count')} paragraphs")
                else:
                    error_msg = result.get('error') or result.get('ai_error') or 'Unknown error'
                    st.error(f"Error: {error_msg}")
                    if result.get('total_pages'):
                        st.info(f"PDF was readable ({result.get('total_pages')} pages), but AI analysis failed")

with tab4:
    st.header("Export Data")
    
    if not st.session_state.extraction_results:
        st.info("No extraction results to export. Process contracts first in the 'Extract Data' tab.")
    else:
        results = st.session_state.extraction_results
        
        st.markdown(f"**{len(results)} contracts** ready for export")
        
        st.divider()
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📊 Excel Export")
            st.markdown("Structured data in spreadsheet format")
            
            if st.button("Generate Excel", type="primary"):
                with st.spinner("Generating Excel file..."):
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    excel_path = OUTPUT_FOLDER / f"contract_data_{timestamp}.xlsx"
                    export_to_excel(results, str(excel_path))
                
                st.success(f"Excel file created!")
                
                with open(excel_path, "rb") as f:
                    st.download_button(
                        label="📥 Download Excel",
                        data=f,
                        file_name=f"contract_data_{timestamp}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
        
        with col2:
            st.subheader("📋 JSON Export")
            st.markdown("Complete data with paragraphs for analysis")
            
            if st.button("Generate JSON", type="primary"):
                with st.spinner("Generating JSON file..."):
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    json_path = OUTPUT_FOLDER / f"contract_data_{timestamp}.json"
                    export_to_json(results, str(json_path))
                
                st.success(f"JSON file created!")
                
                with open(json_path, "rb") as f:
                    st.download_button(
                        label="📥 Download JSON",
                        data=f,
                        file_name=f"contract_data_{timestamp}.json",
                        mime="application/json"
                    )
        
        st.divider()
        
        st.subheader("Preview Data")
        
        preview_data = []
        for r in results:
            if r.get("success"):
                data = r.get("extracted_data", {})
                preview_data.append({
                    "File": r.get("file_name", ""),
                    "Processo ID": r.get("processo_id", ""),
                    "Value": data.get("valor_contrato", ""),
                    "Start Date": data.get("data_inicio", ""),
                    "End Date": data.get("data_fim", ""),
                    "Contractor": data.get("contratante", ""),
                    "Contracted": data.get("contratada", ""),
                    "Type": data.get("tipo_contrato", "")
                })
        
        if preview_data:
            df = pd.DataFrame(preview_data)
            st.dataframe(df, width="stretch")
        else:
            st.warning("No successful extractions to preview")

st.sidebar.header("Configuration")
st.sidebar.markdown(f"**PDF Folder:** `{PDF_FOLDER}`")
st.sidebar.markdown(f"**CSV Path:** `{CSV_PATH}`")
st.sidebar.markdown(f"**Output Folder:** `{OUTPUT_FOLDER}`")

st.sidebar.divider()
st.sidebar.markdown("### About")
st.sidebar.markdown("""
This tool extracts structured data from processo.rio contracts:
- Contract values and dates
- Parties involved
- Contract object/purpose
- Specific clauses
- Full paragraphs for analysis

Data is cross-referenced with your analysis_summary.csv.
""")