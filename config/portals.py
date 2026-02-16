"""
Portal-specific selectors and configuration.
"""

# ContasRio Portal Locators
CONTASRIO_LOCATORS = {
    # Filters
    "year_filter": "select#year-select",
    "company_filter": "input#company-search",
    
    # Company table
    "company_rows": "table.companies tbody tr",
    "company_table": "table.companies",
    
    # Navigation
    "navigation_buttons": "button.nav-button, a.nav-link",
    "back_button": "button.back, a.back",
    
    # Processo links
    "processo_links": "a[href*='processo']",
    
    # Level indicators
    "level_indicator": "div.breadcrumb, nav.breadcrumb",
}

# ContasRio Navigation Levels
CONTASRIO_LEVELS = [
    "favorecido",  # Company level
    "orgao",       # Organization level
    "categoria",   # Category level
    "processo"     # Process level (deepest)
]