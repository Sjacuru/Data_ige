# 📋 PROJECT REORGANIZATION CHECKLIST

Follow these steps **in order** to reorganize your project cleanly.

---

## ✅ PRE-FLIGHT CHECKLIST

Before you start:

- [ ] **Backup your project**
  ```cmd
  cd C:\Users\angel\Documents\GitHub
  xcopy /E /I /Y Data_ige Data_ige_BACKUP
  ```

- [ ] **Close all editors/IDEs** (VS Code, PyCharm, etc.)

- [ ] **Stop any running processes** using your project

- [ ] **Commit your current work to git** (optional but recommended)
  ```cmd
  cd Data_ige
  git add .
  git commit -m "Backup before reorganization"
  ```

---

## 📥 STEP 1: Download the 5 Files

Download these files to your project root: `C:\Users\angel\Documents\GitHub\Data_ige\`

1. ✅ `REORGANIZATION_GUIDE.md` (the guide)
2. ✅ `reorganize_project.bat` (the main script)
3. ✅ `fix_imports.py` (import fixer)
4. ✅ `extract_contract.py` (new workflow)
5. ✅ `extract_publication.py` (new workflow)

**Verify they're in the right place:**
```cmd
cd C:\Users\angel\Documents\GitHub\Data_ige
dir *.bat
dir *.py | findstr "extract"
```

You should see:
```
reorganize_project.bat
extract_contract.py
extract_publication.py
fix_imports.py
```

---

## 🔧 STEP 2: Run the Reorganization Script

Open CMD as Administrator (optional, but safer):

```cmd
cd C:\Users\angel\Documents\GitHub\Data_ige
reorganize_project.bat
```

**What this does:**
- ✅ Creates new folder structure (`domain/`, `infrastructure/`, `application/`)
- ✅ Copies files to new locations
- ✅ Creates all `__init__.py` files
- ✅ Moves old folders to `_archive/old_structure/`

**Expected output:**
```
[STEP 1] ✓ Folder structure created!
[STEP 2] ✓ Domain models moved!
[STEP 3] ✓ Domain services moved!
[STEP 4] ✓ Scrapers moved!
[STEP 5] ✓ Extractors moved!
[STEP 6] ✓ Web utilities moved!
[STEP 7] ✓ Application workflows moved!
[STEP 8] ✓ Tests moved!
[STEP 9] ✓ __init__.py files created!
[STEP 10] ✓ Old structure archived!
```

**⚠️ If you see errors:**
- Check that you're in the right directory
- Make sure files aren't open in other programs
- Try running CMD as Administrator

---

## 🔄 STEP 3: Fix All Imports

```cmd
python fix_imports.py
```

**What this does:**
- ✅ Updates `from conformity.models import` → `from domain.models import`
- ✅ Updates `from core.driver import` → `from infrastructure.web.driver import`
- ✅ Updates `from src.scraper import` → `from infrastructure.scrapers.contasrio.scraper import`
- ✅ Fixes all other import statements

**Expected output:**
```
FIXING IMPORTS IN NEW STRUCTURE
════════════════════════════════════════════════════════════

Scanning: domain/
────────────────────────────────────────────────────────────
✓ Fixed: domain\models\publication.py
✓ Fixed: domain\services\conformity_checker.py

Scanning: infrastructure/
────────────────────────────────────────────────────────────
✓ Fixed: infrastructure\scrapers\contasrio\scraper.py
✓ Fixed: infrastructure\extractors\contract_extractor.py
...

SUMMARY: Fixed 15 out of 23 files
════════════════════════════════════════════════════════════
```

---

## 🧪 STEP 4: Test the New Structure

### Test 1: Check imports
```cmd
python -c "from domain.models.publication import Publication; print('✓ Domain imports work')"
python -c "from infrastructure.web.driver import initialize_driver; print('✓ Infrastructure imports work')"
python -c "from application.workflows.extract_contract import extract_contracts_for_company; print('✓ Application imports work')"
```

**Expected:** All three should print "✓ ... imports work"

### Test 2: Run your application
```cmd
python application\main.py
```

**Expected:** Should run without import errors (may have runtime errors if config needs updating)

### Test 3: Run tests (if you have any)
```cmd
pytest tests_new\
```

---

## 🔍 STEP 5: Verify the New Structure

Check that everything is in the right place:

```cmd
tree /F /A domain
tree /F /A infrastructure
tree /F /A application
```

**Should see:**
```
domain/
├── models/
│   ├── publication.py
│   ├── conformity_result.py
│   └── __init__.py
├── services/
│   ├── conformity_checker.py
│   ├── text_normalizer.py
│   └── __init__.py
└── __init__.py

infrastructure/
├── scrapers/
│   ├── contasrio/
│   │   ├── scraper.py
│   │   ├── downloader.py
│   │   └── parser.py
│   └── doweb/
│       ├── scraper.py
│       └── extractor.py
├── extractors/
│   └── contract_extractor.py
├── web/
│   ├── driver.py
│   ├── captcha.py
│   └── navigation.py
└── persistence/
    └── cache.py

application/
├── workflows/
│   ├── conformity_workflow.py
│   ├── extract_contract.py
│   └── extract_publication.py
├── main.py
└── app.py
```

---

## ✅ STEP 6: Update Your Main Files (Manual)

You'll need to manually update a few things:

### A. Update `application/main.py`

**OLD imports:**
```python
from src.scraper import initialize_driver
from conformity.integration import check_conformity
```

**NEW imports:**
```python
from infrastructure.web.driver import initialize_driver
from application.workflows.conformity_workflow import check_conformity
from application.workflows.extract_contract import extract_contracts_for_company
from application.workflows.extract_publication import extract_publication_for_processo
```

### B. Update `config.py` (if it references old paths)

No changes needed if `config.py` only has constants!

### C. Update `requirements.txt` (if needed)

No changes needed - this is just dependencies!

---

## 🧹 STEP 7: Clean Up (When Everything Works)

### Only do this after confirming everything works!

```cmd
REM Delete archived old structure
rmdir /S /Q _archive

REM Delete temporary workflow files from root
del extract_contract.py
del extract_publication.py
del fix_imports.py
del reorganize_project.bat

REM Optional: Clean up __pycache__
for /d /r . %d in (__pycache__) do @if exist "%d" rmdir /s /q "%d"
```

---

## 🎉 STEP 8: Commit to Git

```cmd
git add .
git commit -m "Reorganize project into clean DDD structure"
git push
```

---

## 🆘 TROUBLESHOOTING

### Problem: "Module not found: domain"

**Solution:**
```cmd
REM Make sure you're running from project root
cd C:\Users\angel\Documents\GitHub\Data_ige

REM Try adding to PYTHONPATH
set PYTHONPATH=%CD%
python application\main.py
```

### Problem: Import errors in specific files

**Solution:**
```cmd
REM Run import fixer again
python fix_imports.py

REM Or manually fix the file using REORGANIZATION_GUIDE.md mapping table
```

### Problem: "File not found" errors

**Solution:**
Check the file is in the new location:
```cmd
dir /s /b filename.py
```

If it's in `_archive\old_structure\`, copy it to the new location.

### Problem: Want to rollback everything

**Solution:**
```cmd
REM Delete new folders
rmdir /S /Q domain infrastructure application tests_new

REM Restore from archive
xcopy /E /I /Y _archive\old_structure\* .

REM Or restore from backup
cd C:\Users\angel\Documents\GitHub
rmdir /S /Q Data_ige
ren Data_ige_BACKUP Data_ige
```

---

## 📊 VERIFICATION CHECKLIST

After reorganization, verify:

- [ ] `domain/` folder exists with models and services
- [ ] `infrastructure/` folder exists with scrapers, extractors, web utilities
- [ ] `application/` folder exists with workflows
- [ ] No import errors when running `python application/main.py`
- [ ] `data/` folder is **untouched** (all your data is safe)
- [ ] Old code is in `_archive/old_structure/`
- [ ] All tests pass (if you have tests)

---

## 🎯 SUCCESS!

If all checkboxes are ticked, your project is now:

✅ Clean and organized  
✅ Following DDD principles  
✅ Easy to navigate  
✅ Easy to test  
✅ Professional structure  
✅ Ready to scale  

**Welcome to clean architecture!** 🚀

---

## 📞 NEED HELP?

If you get stuck:

1. Check `REORGANIZATION_GUIDE.md` for detailed mapping
2. Check `_archive/old_structure/` for original files
3. Restore from `Data_ige_BACKUP` if needed
4. Ask for help with specific error messages

Remember: **Your data is safe in `data/` folder!** Nothing in there was touched.
