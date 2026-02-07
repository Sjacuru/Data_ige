@echo off
REM ============================================================
REM Project Reorganization Script
REM This script will reorganize your Data_ige project into a
REM clean Domain-Driven Design structure
REM ============================================================

echo ========================================
echo PROJECT REORGANIZATION SCRIPT
echo ========================================
echo.
echo This will reorganize your project into:
echo   - domain/       (business logic)
echo   - infrastructure/ (technical code)
echo   - application/   (workflows)
echo   - tests/        (all tests)
echo.
echo Your data folders will NOT be touched!
echo.
pause

REM ============================================================
REM STEP 1: CREATE NEW FOLDER STRUCTURE
REM ============================================================
echo.
echo [STEP 1] Creating new folder structure...

mkdir "domain" 2>nul
mkdir "domain\models" 2>nul
mkdir "domain\services" 2>nul
mkdir "domain\repositories" 2>nul

mkdir "infrastructure" 2>nul
mkdir "infrastructure\scrapers" 2>nul
mkdir "infrastructure\scrapers\contasrio" 2>nul
mkdir "infrastructure\scrapers\doweb" 2>nul
mkdir "infrastructure\extractors" 2>nul
mkdir "infrastructure\ai" 2>nul
mkdir "infrastructure\ai\prompts" 2>nul
mkdir "infrastructure\persistence" 2>nul
mkdir "infrastructure\web" 2>nul

mkdir "application" 2>nul
mkdir "application\workflows" 2>nul

mkdir "tests_new" 2>nul
mkdir "tests_new\unit" 2>nul
mkdir "tests_new\integration" 2>nul

mkdir "_archive" 2>nul
mkdir "_archive\old_structure" 2>nul

echo [STEP 1] ✓ Folder structure created!

REM ============================================================
REM STEP 2: MOVE DOMAIN MODELS
REM ============================================================
echo.
echo [STEP 2] Moving domain models...

copy "conformity\models\publication.py" "domain\models\publication.py" >nul
copy "conformity\models\conformity_result.py" "domain\models\conformity_result.py" >nul

REM Create contract.py model (will need to be created manually)
echo # TODO: Extract Contract model from contract_extractor.py > "domain\models\contract.py"

echo [STEP 2] ✓ Domain models moved!

REM ============================================================
REM STEP 3: MOVE DOMAIN SERVICES
REM ============================================================
echo.
echo [STEP 3] Moving domain services...

copy "conformity\analyzer\publication_conformity.py" "domain\services\conformity_checker.py" >nul
copy "Contract_analisys\text_preprocessor.py" "domain\services\text_normalizer.py" >nul

echo [STEP 3] ✓ Domain services moved!

REM ============================================================
REM STEP 4: MOVE SCRAPERS TO INFRASTRUCTURE
REM ============================================================
echo.
echo [STEP 4] Moving scrapers to infrastructure...

REM ContasRio scraper components
copy "src\scraper.py" "infrastructure\scrapers\contasrio\scraper.py" >nul
copy "src\downloader.py" "infrastructure\scrapers\contasrio\downloader.py" >nul
copy "src\parser.py" "infrastructure\scrapers\contasrio\parser.py" >nul

REM DoWeb scraper components
copy "conformity\scraper\doweb_scraper.py" "infrastructure\scrapers\doweb\scraper.py" >nul
copy "conformity\scraper\doweb_extractor.py" "infrastructure\scrapers\doweb\extractor.py" >nul

echo [STEP 4] ✓ Scrapers moved!

REM ============================================================
REM STEP 5: MOVE EXTRACTORS TO INFRASTRUCTURE
REM ============================================================
echo.
echo [STEP 5] Moving extractors to infrastructure...

copy "Contract_analisys\contract_extractor.py" "infrastructure\extractors\contract_extractor.py" >nul
copy "Contract_analisys\cached_contract_extractor.py" "infrastructure\extractors\cached_contract_extractor.py" >nul
copy "src\document_extractor.py" "infrastructure\extractors\document_extractor.py" >nul

echo [STEP 5] ✓ Extractors moved!

REM ============================================================
REM STEP 6: MOVE CORE/WEB UTILITIES
REM ============================================================
echo.
echo [STEP 6] Moving web utilities...

copy "core\driver.py" "infrastructure\web\driver.py" >nul
copy "core\captcha.py" "infrastructure\web\captcha.py" >nul
copy "core\navigation.py" "infrastructure\web\navigation.py" >nul
copy "core\cache.py" "infrastructure\persistence\cache.py" >nul

echo [STEP 6] ✓ Web utilities moved!

REM ============================================================
REM STEP 7: MOVE APPLICATION WORKFLOWS
REM ============================================================
echo.
echo [STEP 7] Moving application workflows...

copy "conformity\integration.py" "application\workflows\conformity_workflow.py" >nul
copy "main.py" "application\main.py" >nul
copy "app.py" "application\app.py" >nul

echo [STEP 7] ✓ Application workflows moved!

REM ============================================================
REM STEP 8: MOVE TESTS
REM ============================================================
echo.
echo [STEP 8] Moving tests...

xcopy "tests\*.*" "tests_new\integration\" /Y >nul
xcopy "New_Data_ige\tests\*.*" "tests_new\unit\" /E /Y >nul

echo [STEP 8] ✓ Tests moved!

REM ============================================================
REM STEP 9: CREATE __init__.py FILES
REM ============================================================
echo.
echo [STEP 9] Creating __init__.py files...

echo # Domain package > "domain\__init__.py"
echo # Domain models > "domain\models\__init__.py"
echo # Domain services > "domain\services\__init__.py"
echo # Domain repositories > "domain\repositories\__init__.py"

echo # Infrastructure package > "infrastructure\__init__.py"
echo # Scrapers > "infrastructure\scrapers\__init__.py"
echo # ContasRio scraper > "infrastructure\scrapers\contasrio\__init__.py"
echo # DoWeb scraper > "infrastructure\scrapers\doweb\__init__.py"
echo # Extractors > "infrastructure\extractors\__init__.py"
echo # AI clients > "infrastructure\ai\__init__.py"
echo # Persistence > "infrastructure\persistence\__init__.py"
echo # Web utilities > "infrastructure\web\__init__.py"

echo # Application package > "application\__init__.py"
echo # Workflows > "application\workflows\__init__.py"

echo [STEP 9] ✓ __init__.py files created!

REM ============================================================
REM STEP 10: ARCHIVE OLD STRUCTURE
REM ============================================================
echo.
echo [STEP 10] Archiving old structure...

move "src" "_archive\old_structure\src" >nul 2>&1
move "conformity" "_archive\old_structure\conformity" >nul 2>&1
move "Contract_analisys" "_archive\old_structure\Contract_analisys" >nul 2>&1
move "core" "_archive\old_structure\core" >nul 2>&1
move "New_Data_ige" "_archive\old_structure\New_Data_ige" >nul 2>&1
move "scripts" "_archive\old_structure\scripts" >nul 2>&1
move "tests" "_archive\old_structure\tests" >nul 2>&1

echo [STEP 10] ✓ Old structure archived!

REM ============================================================
REM DONE!
REM ============================================================
echo.
echo ========================================
echo ✓ REORGANIZATION COMPLETE!
echo ========================================
echo.
echo NEW STRUCTURE:
echo   domain/           - Business logic
echo   infrastructure/   - Technical implementations
echo   application/      - Workflows and entry points
echo   tests_new/        - All tests
echo.
echo OLD FILES ARCHIVED IN:
echo   _archive/old_structure/
echo.
echo NEXT STEPS:
echo   1. Review the new structure
echo   2. Run fix_imports.py to update all imports
echo   3. Test your application
echo   4. Delete _archive folder when confirmed working
echo.
pause
