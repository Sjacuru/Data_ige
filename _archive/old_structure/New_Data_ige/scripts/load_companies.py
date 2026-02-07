"""
load_companies.py - Load companies without scraping

Location: NEW_DATA_IGE/scripts/load_companies.py

Run: python -m New_Data_ige.scripts.load_companies
"""

from New_Data_ige.infrastructure.persistence.json_company_repository import JsonCompanyRepository


def main():
    print("\n" + "="*70)
    print("📂 LOAD COMPANIES - No Scraping")
    print("="*70)
    
    # Load from repository
    repo = JsonCompanyRepository("data/companies.json")
    
    companies = repo.find_all()
    
    if not companies:
        print("\n⚠️  No companies found. Run scrape_and_save.py first.")
        return
    
    print(f"\n✅ Loaded: {len(companies)} companies")
    
    # Statistics
    total_contratado = sum(
        float(c.total_contratado.replace(".", "").replace(",", "."))
        for c in companies
        if c.total_contratado
    )
    
    print(f"\n📊 Statistics:")
    print(f"   Total Companies: {len(companies)}")
    print(f"   Total Contracted: R$ {total_contratado:,.2f}")
    
    # Show first 10
    print(f"\n👥 First 10 Companies:")
    for i, company in enumerate(companies[:10], 1):
        print(f"   {i}. {company.id} - {company.name[:40]}...")
    
    # Search example
    print(f"\n🔍 Search Example:")
    search_id = input("   Enter company ID to search (or Enter to skip): ")
    if search_id:
        found = repo.find_by_id(search_id)
        if found:
            print(f"\n   ✅ Found:")
            print(f"      ID: {found.id}")
            print(f"      Name: {found.name}")
            print(f"      Total: {found.total_contratado}")
        else:
            print(f"\n   ❌ Not found")
    
    print("\n" + "="*70)


if __name__ == "__main__":
    main()